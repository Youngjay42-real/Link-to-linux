package com.example.linktolinux.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val DarkColorScheme = darkColorScheme(
    primary = androidx.compose.ui.graphics.Color(0xFF64B5F6),
    secondary = androidx.compose.ui.graphics.Color(0xFF90CAF9),
    tertiary = androidx.compose.ui.graphics.Color(0xFF80CBC4)
)

private val LightColorScheme = lightColorScheme(
    primary = androidx.compose.ui.graphics.Color(0xFF1976D2),
    secondary = androidx.compose.ui.graphics.Color(0xFF42A5F5),
    tertiary = androidx.compose.ui.graphics.Color(0xFF26A69A)
)

@Composable
fun LinkToLinuxTheme(
    darkTheme: Boolean = false,
    content: @Composable () -> Unit
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme
    MaterialTheme(
        colorScheme = colorScheme,
        content = content
    )
}
