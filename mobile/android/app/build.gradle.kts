import java.util.Properties
import java.io.FileInputStream

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Load the upload-key keystore credentials from android/key.properties
// (gitignored). Required by Play Store: release builds MUST be signed
// with the upload key, not the debug key. Google Play App Signing
// re-signs server-side with the production key — but the AAB you
// upload MUST come signed with the registered upload key.
//   https://docs.flutter.dev/deployment/android#signing-the-app
val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    namespace = "com.solvrlabs.agent_playground"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_11.toString()
    }

    defaultConfig {
        applicationId = "com.solvrlabs.agentplayground"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName

        // flutter_appauth (GitHub OAuth) requires this scheme to be
        // baked into the AppAuth RedirectUriReceiverActivity at build
        // time. Without it, the Custom Tab redirect to
        // solvrlabs://oauth/github after a successful GitHub authorize
        // is never claimed by AppAuth's native listener and the
        // authorize() Future hangs forever — UI stays stuck on the
        // login screen with the button disabled.
        // AndroidManifest.xml lines 27-40 also declare the intent-filter,
        // but Gradle's manifestPlaceholders is what wires AppAuth's
        // library activity to that scheme.
        manifestPlaceholders["appAuthRedirectScheme"] = "solvrlabs"
    }

    signingConfigs {
        create("release") {
            keyAlias = keystoreProperties["keyAlias"] as String?
            keyPassword = keystoreProperties["keyPassword"] as String?
            storeFile = (keystoreProperties["storeFile"] as String?)?.let { file(it) }
            storePassword = keystoreProperties["storePassword"] as String?
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
        }
    }
}

flutter {
    source = "../.."
}