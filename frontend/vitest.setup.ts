// Vitest ortamını hazırlar: jsdom `crypto.subtle` sağlamaz; Node'un
// WebCrypto'sunu global olarak yayınlayarak cleanDicom/cleanHea/hashAnonId
// fonksiyonlarının gerçek kriptoyla çalışmasını sağlar.
import { webcrypto } from "node:crypto";

if (!globalThis.crypto || !(globalThis.crypto as Crypto).subtle) {
  Object.defineProperty(globalThis, "crypto", {
    value: webcrypto,
    configurable: true,
  });
}
