// JNI-обёртка над llama.cpp: загрузка GGUF, генерация с потоковой отдачей токенов, повторное использование кэша общего начала промпта.
#include <jni.h>
#include <android/log.h>
#include <string>
#include <vector>
#include <atomic>
#include <algorithm>
#include "llama.h"

#define LOG(...) __android_log_print(ANDROID_LOG_INFO, "oallm", __VA_ARGS__)

struct Eng {
    llama_model* model = nullptr; llama_context* ctx = nullptr; const llama_vocab* vocab = nullptr;
    std::vector<llama_token> cache;   // что сейчас лежит в KV-кэше
    std::atomic<bool> stop{false};
};

static bool g_init = false;
// длина самого длинного префикса, заканчивающегося на границе символа UTF-8
static size_t utf8_prefix(const std::string& s) {
    size_t n = s.size(); if (!n) return 0;
    size_t i = n; int back = 0;
    while (i > 0 && back < 4 && ((unsigned char)s[i - 1] & 0xC0) == 0x80) { i--; back++; }
    if (i == 0) return n;
    unsigned char c = (unsigned char)s[i - 1]; int need = c >= 0xF0 ? 4 : c >= 0xE0 ? 3 : c >= 0xC0 ? 2 : 1;
    return (need > back + 1) ? i - 1 : n;
}

extern "C" JNIEXPORT jlong JNICALL Java_openagent_app_com_LocalLlm_nLoad(JNIEnv* env, jobject, jstring jpath, jint nCtx, jint threads) {
    if (!g_init) { llama_backend_init(); g_init = true; }
    const char* p = env->GetStringUTFChars(jpath, nullptr);
    llama_model_params mp = llama_model_default_params();
    llama_model* m = llama_model_load_from_file(p, mp);
    env->ReleaseStringUTFChars(jpath, p);
    if (!m) return 0;
    llama_context_params cp = llama_context_default_params();
    cp.n_ctx = nCtx; cp.n_batch = 512; cp.n_ubatch = 512; cp.n_threads = threads; cp.n_threads_batch = threads;
    llama_context* c = llama_init_from_model(m, cp);
    if (!c) { llama_model_free(m); return 0; }
    auto* e = new Eng(); e->model = m; e->ctx = c; e->vocab = llama_model_get_vocab(m);
    return (jlong)e;
}

extern "C" JNIEXPORT void JNICALL Java_openagent_app_com_LocalLlm_nFree(JNIEnv*, jobject, jlong h) {
    auto* e = (Eng*)h; if (!e) return;
    llama_free(e->ctx); llama_model_free(e->model); delete e;
}

extern "C" JNIEXPORT void JNICALL Java_openagent_app_com_LocalLlm_nStop(JNIEnv*, jobject, jlong h) { if (h) ((Eng*)h)->stop = true; }

// Возвращает полный текст ответа; cb.onToken(String): Boolean — false останавливает. Ошибка → строка, начинающаяся с "\u0001ERR".
extern "C" JNIEXPORT jstring JNICALL Java_openagent_app_com_LocalLlm_nGenerate(JNIEnv* env, jobject, jlong h, jstring jprompt, jint maxTokens, jfloat temp, jfloat topP, jfloat repeat, jobject cb) {
    auto* e = (Eng*)h; if (!e) return env->NewStringUTF("\u0001ERR нет модели");
    e->stop = false;
    const char* ps = env->GetStringUTFChars(jprompt, nullptr); std::string prompt(ps); env->ReleaseStringUTFChars(jprompt, ps);
    int cap = (int)prompt.size() + 16; std::vector<llama_token> toks(cap);
    int n = llama_tokenize(e->vocab, prompt.c_str(), (int)prompt.size(), toks.data(), cap, true, true);
    if (n < 0) { toks.resize(-n); n = llama_tokenize(e->vocab, prompt.c_str(), (int)prompt.size(), toks.data(), (int)toks.size(), true, true); }
    if (n <= 0) return env->NewStringUTF("\u0001ERR токенизация");
    toks.resize(n);
    int nctx = (int)llama_n_ctx(e->ctx);
    if (n + 8 >= nctx) return env->NewStringUTF("\u0001ERR запрос длиннее окна контекста");
    int room = nctx - n - 1; if (maxTokens > room) maxTokens = room;
    // общий префикс с прошлым запросом остаётся в кэше
    size_t common = 0; while (common < e->cache.size() && common < toks.size() - 1 && e->cache[common] == toks[common]) common++;
    llama_memory_t mem = llama_get_memory(e->ctx);
    llama_memory_seq_rm(mem, 0, (llama_pos)common, -1);
    e->cache.resize(common);
    // дописываем остаток промпта пачками
    for (size_t i = common; i < toks.size();) {
        int k = (int)std::min<size_t>(512, toks.size() - i);
        llama_batch b = llama_batch_get_one(&toks[i], k);
        if (llama_decode(e->ctx, b) != 0) { e->cache.clear(); llama_memory_seq_rm(mem, 0, -1, -1); return env->NewStringUTF("\u0001ERR decode"); }
        for (int j = 0; j < k; j++) e->cache.push_back(toks[i + j]);
        i += k;
    }
    llama_sampler* sm = llama_sampler_chain_init(llama_sampler_chain_default_params());
    if (repeat > 1.0f) llama_sampler_chain_add(sm, llama_sampler_init_penalties(llama_vocab_n_tokens(e->vocab), 256, repeat, 0.0f, 0.0f));
    if (temp <= 0.0f) llama_sampler_chain_add(sm, llama_sampler_init_greedy());
    else { llama_sampler_chain_add(sm, llama_sampler_init_top_k(40)); llama_sampler_chain_add(sm, llama_sampler_init_top_p(topP, 1)); llama_sampler_chain_add(sm, llama_sampler_init_temp(temp)); llama_sampler_chain_add(sm, llama_sampler_init_dist(0xC0FFEE)); }
    jclass cls = env->GetObjectClass(cb); jmethodID mid = env->GetMethodID(cls, "onToken", "(Ljava/lang/String;)Z");
    std::string out, pending; char buf[256];
    for (int i = 0; i < maxTokens && !e->stop; i++) {
        llama_token t = llama_sampler_sample(sm, e->ctx, -1);
        if (llama_vocab_is_eog(e->vocab, t)) break;
        llama_sampler_accept(sm, t);
        int len = llama_token_to_piece(e->vocab, t, buf, sizeof buf, 0, false);
        if (len > 0) pending.append(buf, len);
        size_t cut = utf8_prefix(pending);
        if (cut == 0) { llama_batch b = llama_batch_get_one(&t, 1); if (llama_decode(e->ctx, b) != 0) break; e->cache.push_back(t); continue; }
        std::string piece = pending.substr(0, cut); pending.erase(0, cut);
        out += piece;
        jstring js = env->NewStringUTF(piece.c_str());
        jboolean go = env->CallBooleanMethod(cb, mid, js); env->DeleteLocalRef(js);
        if (env->ExceptionCheck()) { env->ExceptionClear(); break; }
        if (!go) { llama_batch b = llama_batch_get_one(&t, 1); if (llama_decode(e->ctx, b) == 0) e->cache.push_back(t); break; }
        llama_batch b = llama_batch_get_one(&t, 1);
        if (llama_decode(e->ctx, b) != 0) break;
        e->cache.push_back(t);
    }
    llama_sampler_free(sm);
    return env->NewStringUTF(out.c_str());
}
