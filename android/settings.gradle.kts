pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
    // Versions live HERE, so every `id("...")` in any build file resolves without its own version.
    plugins {
        id("com.android.application") version "8.5.2"
        id("org.jetbrains.kotlin.android") version "1.9.24"
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "NeuroStrike"
include(":app")
