# Pulsar Anonymizer — WASM Portu

Modül 1'in tarayıcı tarafı derlemesi. Rust + `wasm-bindgen` + `dicom-rs`
ile `cleaner.py` mantığının birebir portu hedeflenir.

## Derleme

```bash
cargo install wasm-pack
cd anonymizer/dicom_cleaner/wasm
wasm-pack build --target web --out-dir pkg
```

## Beklenen API (frontend/lib/anonymizer-client.ts ile sözleşme)

```rust
#[wasm_bindgen]
pub struct PulsarAnonymizer;

#[wasm_bindgen]
impl PulsarAnonymizer {
    /// DICOM byte stream'i anonimleştirir; (bytes, rapor) döner.
    pub fn clean_dicom(&self, data: &[u8], salt: &str) -> JsValue;
    /// Türkçe metindeki PII'yi maskeler; (masked_text, findings) döner.
    pub fn mask_pii(&self, text: &str) -> JsValue;
}
```

Fallback: `pkg` yoksa frontend Pyodide ile `pydicom` + `pii_nlp` yükler.
Her iki yolda da ham veri ağdan geçmez (Zero-Knowledge Architecture).
