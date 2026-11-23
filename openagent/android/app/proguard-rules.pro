# OpenAgent: правила R8 (без обфускации — только сжатие и оптимизация)
-dontobfuscate
-keepattributes *Annotation*, InnerClasses, Signature, RuntimeVisibleAnnotations, EnclosingMethod
# kotlinx.serialization
-keepclassmembers class openagent.app.com.** { *** Companion; }
-keepclasseswithmembers class openagent.app.com.** { kotlinx.serialization.KSerializer serializer(...); }
-keep,includedescriptorclasses class openagent.app.com.**$$serializer { *; }
-keep class openagent.app.com.** implements kotlinx.serialization.KSerializer { *; }
# OkHttp / Okio
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
# Coil SVG / AndroidSVG
-dontwarn com.caverock.androidsvg.**
-keep class com.caverock.androidsvg.** { *; }
# WorkManager worker
-keep class openagent.app.com.UpdatesWorker { *; }
# WebView JS-мост капчи
-keepclassmembers class * { @android.webkit.JavascriptInterface <methods>; }
