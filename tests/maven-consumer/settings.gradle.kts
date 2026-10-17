rootProject.name = "nomercy-maven-consumer-proof"

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        exclusiveContent {
            forRepository { maven("https://repo.nomercy.tv/maven") }
            filter { includeGroup("tv.nomercy") }
        }
    }
}
