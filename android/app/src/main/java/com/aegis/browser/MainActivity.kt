package com.aegis.browser

import android.os.Bundle
import android.webkit.WebView
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView

class MainActivity : ComponentActivity() {
    private var ownedWebView: WebView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            var address by remember { mutableStateOf("https://www.bing.com") }
            var webViewRef: WebView? by remember { mutableStateOf(null) }
            val engine = webViewRef?.let { BrowserEngine(it) }

            Column(modifier = Modifier.fillMaxSize()) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(8.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    OutlinedTextField(
                        value = address,
                        onValueChange = { address = it },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        label = { Text("地址") }
                    )
                    Button(onClick = { engine?.load(address) }) { Text("打开") }
                }
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Button(onClick = { webViewRef?.goBack() }) { Text("后退") }
                    Button(onClick = { webViewRef?.goForward() }) { Text("前进") }
                    Button(onClick = { webViewRef?.reload() }) { Text("刷新") }
                }
                AndroidView(
                    modifier = Modifier.weight(1f),
                    factory = { context ->
                        WebView(context).also { view ->
                            webViewRef = view
                            ownedWebView = view
                            BrowserEngine(view).configure()
                            BrowserEngine(view).load(address)
                        }
                    },
                    update = { webViewRef = it }
                )
            }
        }
    }

    override fun onDestroy() {
        // WebView 持有 Chromium 资源，必须在 Activity 销毁时主动释放。
        ownedWebView?.apply {
            stopLoading()
            loadUrl("about:blank")
            clearHistory()
            removeAllViews()
            destroy()
        }
        ownedWebView = null
        super.onDestroy()
    }
}
