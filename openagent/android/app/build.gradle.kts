plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "openagent.app.com"
    compileSdk = 35

    defaultConfig {
        applicationId = "openagent.app.com"
        minSdk = 26
        targetSdk = 35
        versionCode = 7
        versionName = "7.0"
        ndk { abiFilters += listOf("arm64-v8a") }   // современные телефоны (64 бит); без 32-битных и x86 — APK заметно меньше (ONNX Runtime и MediaPipe тяжёлые)
        // Адрес вашего сервера и Web client ID для входа через Google (из google-services.json)
        buildConfigField("String", "SERVER_URL", "\"https://openagents.duckdns.org\"")
        buildConfigField("String", "GOOGLE_WEB_CLIENT_ID", "\"199268040211-o81u4shtd4trbemiorddnjs3jm7acd9g.apps.googleusercontent.com\"")
    }

    signingConfigs {
        create("openagent") {
            storeFile = file("openagent.jks")
            storePassword = "openagent123"
            keyAlias = "openagent"
            keyPassword = "openagent123"
        }
    }

    buildTypes {
        debug { signingConfig = signingConfigs.getByName("openagent") }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("openagent")
        }
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    testOptions { unitTests.isIncludeAndroidResources = true }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
    androidResources { noCompress += "tflite" }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.14.1")
    testImplementation("androidx.compose.ui:ui-test-junit4")
    testImplementation("androidx.test:core-ktx:1.6.1")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation("androidx.exifinterface:exifinterface:1.3.7")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.animation:animation")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("io.coil-kt:coil-svg:2.7.0")
    implementation("com.caverock:androidsvg-aar:1.4")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("org.tensorflow:tensorflow-lite:2.16.1")
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.22.0")          // голос (ReDimNet2) и лицо (MobileFaceNet)
    implementation("com.google.mediapipe:tasks-vision:0.10.21")                     // детектор лица и жесты (✌️)      // YAMNet для «двойного хлопка»
    implementation("androidx.camera:camera-camera2:1.4.1")
    implementation("androidx.camera:camera-lifecycle:1.4.1")
    implementation("androidx.camera:camera-view:1.4.1")
    implementation("androidx.profileinstaller:profileinstaller:1.4.1")
    implementation("androidx.credentials:credentials:1.3.0")
    implementation("androidx.credentials:credentials-play-services-auth:1.3.0")
    implementation("com.google.android.libraries.identity.googleid:googleid:1.1.1")
}
