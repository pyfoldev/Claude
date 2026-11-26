package app.veil.vpn

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/** Конфиг (с приватным ключом) хранится зашифрованно. */
class Store(ctx: Context) {
    private val prefs: SharedPreferences = try {
        EncryptedSharedPreferences.create(
            ctx, "veil_secure",
            MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) { ctx.getSharedPreferences("veil_plain", Context.MODE_PRIVATE) }

    var conf: String?
        get() = prefs.getString("conf", null)
        set(v) { prefs.edit().putString("conf", v).apply() }
}
