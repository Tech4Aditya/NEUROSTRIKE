package com.neurostrike

import org.json.JSONObject

/** A radar contact: world position of a target the PC's detector found. */
data class Contact(val id: Int, val x: Float, val y: Float, val conf: Float, val age: Float)

data class GameState(
    val px: Float = 0f, val py: Float = 0f, val h: Float = 0f,
    val hp: Int = 100, val score: Int = 0, val hurt: Int = 0, val alive: Boolean = true,
    val src: String = "--", val ms: Int = 0,
    val ammo: Int = 30, val mag: Int = 30, val rel: Float = -1f, val spr: Int = 0, val stam: Float = 1f,
    val contacts: List<Contact> = emptyList(),
)

fun parseState(text: String): GameState? = try {
    val o = JSONObject(text)
    if (o.optString("t") != "state") null else {
        val arr = o.optJSONArray("contacts")
        val contacts = buildList {
            if (arr != null) for (i in 0 until arr.length()) {
                val c = arr.getJSONObject(i)
                add(Contact(c.getInt("id"), c.getDouble("x").toFloat(), c.getDouble("y").toFloat(),
                    c.optDouble("c", 1.0).toFloat(), c.optDouble("a", 0.0).toFloat()))
            }
        }
        GameState(
            o.optDouble("px").toFloat(), o.optDouble("py").toFloat(), o.optDouble("h").toFloat(),
            o.optInt("hp", 100), o.optInt("score"), o.optInt("hurt"), o.optBoolean("alive", true),
            o.optString("src", "--"), o.optInt("ms"),
            o.optInt("ammo", 30), o.optInt("mag", 30), o.optDouble("rel", -1.0).toFloat(),
            o.optInt("spr"), o.optDouble("stam", 1.0).toFloat(), contacts,
        )
    }
} catch (e: Exception) { null }
