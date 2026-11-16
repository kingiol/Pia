package com.pia.mobile

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val LightColors = lightColorScheme(
    primary = Color(0xFF146B5F),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE3F1EB),
    onPrimaryContainer = Color(0xFF104F46),
    secondary = Color(0xFF525252),
    secondaryContainer = Color(0xFFF4F4F5),
    onSecondaryContainer = Color(0xFF171717),
    tertiary = Color(0xFF525252),
    background = Color(0xFFFAFAFA),
    onBackground = Color(0xFF171717),
    surface = Color.White,
    onSurface = Color(0xFF171717),
    surfaceVariant = Color(0xFFF4F4F5),
    onSurfaceVariant = Color(0xFF525252),
    surfaceTint = Color.Transparent,
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color(0xFFFAFAFA),
    surfaceContainer = Color(0xFFF4F4F5),
    surfaceContainerHigh = Color(0xFFEEEEEF),
    surfaceContainerHighest = Color(0xFFE4E4E7),
    outline = Color(0xFF737373),
    outlineVariant = Color(0xFFE4E4E7),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF9ED8C5),
    onPrimary = Color(0xFF063E32),
    primaryContainer = Color(0xFF203C33),
    onPrimaryContainer = Color(0xFFBCECD9),
    secondary = Color(0xFFA1A1A6),
    secondaryContainer = Color(0xFF232325),
    onSecondaryContainer = Color(0xFFEDEDED),
    tertiary = Color(0xFFA1A1A6),
    background = Color(0xFF141415),
    onBackground = Color(0xFFEDEDED),
    surface = Color(0xFF19191B),
    onSurface = Color(0xFFEDEDED),
    surfaceVariant = Color(0xFF232325),
    onSurfaceVariant = Color(0xFFA1A1A6),
    surfaceTint = Color.Transparent,
    surfaceContainerLowest = Color(0xFF0F0F10),
    surfaceContainerLow = Color(0xFF19191B),
    surfaceContainer = Color(0xFF1D1D1F),
    surfaceContainerHigh = Color(0xFF232325),
    surfaceContainerHighest = Color(0xFF2B2B2D),
    outline = Color(0xFF85858B),
    outlineVariant = Color(0xFF343436),
)

private val DefaultType = Typography()
private val PiaTypography = Typography(
    displayLarge = DefaultType.displayLarge.copy(letterSpacing = 0.sp),
    displayMedium = DefaultType.displayMedium.copy(letterSpacing = 0.sp),
    displaySmall = DefaultType.displaySmall.copy(letterSpacing = 0.sp),
    headlineLarge = DefaultType.headlineLarge.copy(letterSpacing = 0.sp),
    headlineMedium = DefaultType.headlineMedium.copy(letterSpacing = 0.sp),
    headlineSmall = DefaultType.headlineSmall.copy(letterSpacing = 0.sp),
    titleLarge = DefaultType.titleLarge.copy(letterSpacing = 0.sp),
    titleMedium = DefaultType.titleMedium.copy(letterSpacing = 0.sp),
    titleSmall = DefaultType.titleSmall.copy(letterSpacing = 0.sp),
    bodyLarge = DefaultType.bodyLarge.copy(letterSpacing = 0.sp),
    bodyMedium = DefaultType.bodyMedium.copy(letterSpacing = 0.sp),
    bodySmall = DefaultType.bodySmall.copy(letterSpacing = 0.sp),
    labelLarge = DefaultType.labelLarge.copy(letterSpacing = 0.sp),
    labelMedium = DefaultType.labelMedium.copy(letterSpacing = 0.sp),
    labelSmall = DefaultType.labelSmall.copy(letterSpacing = 0.sp),
)

@Composable
internal fun PiaTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (isSystemInDarkTheme()) DarkColors else LightColors,
        typography = PiaTypography,
        shapes = Shapes(
            extraSmall = RoundedCornerShape(4.dp),
            small = RoundedCornerShape(4.dp),
            medium = RoundedCornerShape(8.dp),
            large = RoundedCornerShape(8.dp),
            extraLarge = RoundedCornerShape(8.dp),
        ),
        content = content,
    )
}
