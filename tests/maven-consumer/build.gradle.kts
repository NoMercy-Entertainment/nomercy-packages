plugins { base }

val release = "0.2.10"
val coordinates = listOf(
    "nomercy-video-player-compose",
    "nomercy-video-player-compose-android",
    "nomercy-video-player-compose-jvm",
    "nomercy-player-core-kmp",
    "nomercy-player-core-kmp-android",
    "nomercy-player-core-kmp-jvm",
)

val probes = coordinates.associateWith { artifact ->
    configurations.create("probe" + artifact.split('-').joinToString("") { it.replaceFirstChar(Char::uppercase) }) {
        isTransitive = false
    }.also {
        val suffix = when {
            artifact.endsWith("-android") -> "@aar"
            artifact.endsWith("-jvm") -> "@jar"
            else -> ""
        }
        dependencies.add(it.name, "tv.nomercy:$artifact:$release$suffix")
    }
}

tasks.register("resolveMaven") {
    doLast {
        probes.forEach { (artifact, configuration) ->
            val files = configuration.resolve()
            check(files.isNotEmpty()) { "$artifact resolved no files" }
            if (artifact.endsWith("-android")) {
                check(files.any { it.extension == "aar" }) { "$artifact resolved no AAR" }
            }
            if (artifact.endsWith("-jvm")) {
                check(files.any { it.extension == "jar" }) { "$artifact resolved no JAR" }
            }
            println("$artifact: ${files.joinToString { it.name }}")
        }
    }
}
