package app.staika

import android.content.Context
import android.content.SharedPreferences
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Настройки и токены. Токены лежат в EncryptedSharedPreferences (ключ в Android Keystore). */
object Prefs {
    private var sp: SharedPreferences? = null

    fun init(ctx: Context) {
        sp = try {
            val key = MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
            EncryptedSharedPreferences.create(ctx, "staika_secure", key,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV, EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM)
        } catch (e: Exception) { ctx.getSharedPreferences("staika_plain", Context.MODE_PRIVATE) }
    }

    private fun get(k: String, d: String? = null) = sp?.getString(k, d) ?: d
    private fun put(k: String, v: String?) { sp?.edit()?.apply { if (v == null) remove(k) else putString(k, v) }?.apply() }

    var server: String get() = get("server", "")!!; set(v) = put("server", v)
    var access: String? get() = get("access"); set(v) = put("access", v)
    var refresh: String? get() = get("refresh"); set(v) = put("refresh", v)
    var voiceModel: String get() = get("voiceModel", "Claude Haiku 4.5")!!; set(v) = put("voiceModel", v)
    var voiceLang: String get() = get("voiceLang", "ru")!!; set(v) = put("voiceLang", v)
}

class ApiError(val code: String, message: String, val status: Int = 0) : Exception(message)

object Api {
    val http: OkHttpClient = OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS).readTimeout(70, TimeUnit.SECONDS)
        .pingInterval(25, TimeUnit.SECONDS).build()
    private val JSON = "application/json; charset=utf-8".toMediaType()
    private val refreshLock = Mutex()

    /** Приводит ввод пользователя к адресу сервера: схема, без хвостового слеша. */
    fun normalizeUrl(raw: String): String {
        var u = raw.trim().trimEnd('/')
        if (u.isEmpty()) return ""
        if (!u.startsWith("http://") && !u.startsWith("https://")) u = "https://$u"
        return u
    }

    fun wsUrl(path: String) = Prefs.server.replaceFirst("http", "ws") + path

    private suspend fun raw(method: String, path: String, body: JSONObject?, auth: Boolean): Pair<Int, String> = withContext(Dispatchers.IO) {
        if (Prefs.server.isEmpty()) throw ApiError("no_server", "Не указан адрес сервера")
        val rb = Request.Builder()
        try { rb.url(Prefs.server + path) } catch (e: IllegalArgumentException) { throw ApiError("bad_url", "Неверный адрес сервера") }
        if (auth) Prefs.access?.let { rb.header("Authorization", "Bearer $it") }
        val needsBody = method == "POST" || method == "PUT" || method == "PATCH"
        rb.method(method, if (needsBody) (body ?: JSONObject()).toString().toRequestBody(JSON) else null)
        try {
            http.newCall(rb.build()).execute().use { it.code to (it.body?.string() ?: "") }
        } catch (e: IOException) {
            throw ApiError("network", "Нет связи с сервером")
        }
    }

    suspend fun call(method: String, path: String, body: JSONObject? = null, auth: Boolean = true): Any? {
        var (code, text) = raw(method, path, body, auth)
        if (code == 401 && auth && Prefs.refresh != null && refreshTokens()) {
            val r = raw(method, path, body, auth); code = r.first; text = r.second
        }
        if (code !in 200..299) {
            val j = try { JSONObject(text) } catch (e: Exception) { null }
            if (code == 401 && auth) Repo.onSessionExpired()
            throw ApiError(j?.optString("error") ?: "http_$code", j?.optString("message")?.takeIf { it.isNotEmpty() } ?: "Ошибка сервера ($code)", code)
        }
        return if (text.isBlank()) null else JSONTokener(text).nextValue()
    }

    suspend fun obj(method: String, path: String, body: JSONObject? = null, auth: Boolean = true) =
        call(method, path, body, auth) as? JSONObject ?: JSONObject()

    suspend fun arr(method: String, path: String, body: JSONObject? = null) = call(method, path, body) as? JSONArray ?: JSONArray()

    /** Обновляет access-токен по refresh. false: сессия закрыта или нет сети. */
    suspend fun refreshTokens(): Boolean = refreshLock.withLock {
        val rt = Prefs.refresh ?: return false
        val before = Prefs.access
        val (code, text) = try { raw("POST", "/api/auth/refresh", JSONObject().put("refreshToken", rt), false) } catch (e: ApiError) { return false }
        if (code in 200..299) { saveTokens(JSONObject(text)); return true }
        if (code == 401) { if (Prefs.access == before) { Prefs.access = null; Prefs.refresh = null } }
        false
    }

    fun saveTokens(j: JSONObject) { Prefs.access = j.getString("accessToken"); Prefs.refresh = j.getString("refreshToken") }

    /** Свежий access-токен для WebSocket (не истёк в ближайшую минуту). */
    suspend fun freshToken(): String? {
        val t = Prefs.access ?: return null
        val exp = try {
            JSONObject(String(Base64.decode(t.split('.')[1], Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP))).getLong("exp")
        } catch (e: Exception) { 0L }
        if (exp * 1000 - System.currentTimeMillis() < 60_000) refreshTokens()
        return Prefs.access
    }

    // ---------- авторизация ----------
    suspend fun config() = obj("GET", "/api/config", auth = false)

    private suspend fun tokens(path: String, body: JSONObject): Me {
        val j = obj("POST", path, body, auth = false)
        saveTokens(j)
        return parseMe(j.getJSONObject("user"))
    }
    suspend fun login(email: String, pass: String) = tokens("/api/auth/login", JSONObject().put("email", email).put("password", pass))
    suspend fun register(email: String, pass: String) = tokens("/api/auth/register", JSONObject().put("email", email).put("password", pass))
    suspend fun codeLogin(email: String, code: String) = tokens("/api/auth/code/verify", JSONObject().put("email", email).put("code", code))
    suspend fun google(idToken: String) = tokens("/api/auth/google", JSONObject().put("idToken", idToken))
    suspend fun requestCode(email: String) { obj("POST", "/api/auth/code/request", JSONObject().put("email", email), auth = false) }
    suspend fun forgot(email: String) { obj("POST", "/api/auth/password/forgot", JSONObject().put("email", email), auth = false) }
    suspend fun resetPassword(email: String, code: String, pass: String) {
        obj("POST", "/api/auth/password/reset", JSONObject().put("email", email).put("code", code).put("newPassword", pass), auth = false)
    }
    suspend fun logout() {
        val rt = Prefs.refresh
        if (rt != null) try { obj("POST", "/api/auth/logout", JSONObject().put("refreshToken", rt), auth = false) } catch (_: Exception) {}
        Prefs.access = null; Prefs.refresh = null
    }
}

fun parseMe(j: JSONObject) = Me(j.getString("id"), j.getString("email"), j.optString("name"), j.optString("role", "member"), j.optBoolean("emailVerified"))
