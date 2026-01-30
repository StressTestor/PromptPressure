use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use std::sync::Mutex;

struct SidecarState {
    #[allow(dead_code)]
    process: Option<tauri_plugin_shell::process::CommandChild>,
}

/// Start the Python sidecar API server
#[tauri::command]
async fn start_sidecar(app: tauri::AppHandle, state: tauri::State<'_, Mutex<SidecarState>>) -> Result<String, String> {
    let sidecar = app.shell()
        .sidecar("promptpressure-sidecar")
        .map_err(|e| format!("Failed to create sidecar command: {}", e))?
        .args(["--desktop"]);

    let (mut rx, child) = sidecar
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

    // Store the child process
    {
        let mut s = state.lock().unwrap();
        s.process = Some(child);
    }

    // Wait for startup message
    tokio::spawn(async move {
        while let Some(event) = rx.recv().await {
            if let tauri_plugin_shell::process::CommandEvent::Stdout(line) = event {
                println!("Sidecar: {}", String::from_utf8_lossy(&line));
            }
        }
    });

    Ok("Sidecar started on http://127.0.0.1:9876".to_string())
}

/// Check if the sidecar is running
#[tauri::command]
async fn check_sidecar_health() -> Result<bool, String> {
    let client = reqwest::Client::new();
    match client.get("http://127.0.0.1:9876/api/health")
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
    {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}

/// Get available local models from Ollama
#[tauri::command]
async fn list_ollama_models() -> Result<serde_json::Value, String> {
    let client = reqwest::Client::new();
    match client.get("http://localhost:11434/api/tags")
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        Ok(resp) => {
            let json: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
            Ok(json)
        }
        Err(e) => Err(format!("Ollama not available: {}", e)),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(Mutex::new(SidecarState { process: None }))
        .invoke_handler(tauri::generate_handler![
            start_sidecar,
            check_sidecar_health,
            list_ollama_models
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
