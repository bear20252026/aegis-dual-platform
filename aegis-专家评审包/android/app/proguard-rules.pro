# Keep WebView bridge and Activity entry points stable.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keep public class com.aegis.browser.MainActivity { *; }
