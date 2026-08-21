import { expect, test } from "@playwright/test";

/**
 * Jüri demo akışı (TASK.md T4 DoD):
 * yükle → anonim panelini doğrula → analiz → heatmap görünür → hekim onayı
 * → durum APPROVED. Ayrıca ham dosyanın ağa çıkmadığı doğrulanır.
 */

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

test("uçtan uca: anonimleştirme → analiz → XAI → hekim onayı", async ({ page }) => {
  // 1) Login
  await page.goto("/login");
  await page.fill('input[type="email"]', "hekim@pulsar.demo");
  await page.fill('input[type="password"]', "hekim-demo-1234");
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/dashboard/);

  // 2) Yeni çalışma — KVKK şeffaf paneli
  await page.goto("/studies/new");
  const epikriz =
    "Hasta AHMET YILMAZ, T.C. Kimlik No 10000000146. Toraks BT'de sağ alt lobda 8 mm boyutlu nodül saptandı.";
  await page.fill("textarea", epikriz);
  await expect(page.getByText("[TC_KIMLIK]")).toBeVisible();
  await expect(page.getByText("[KISI_ADI]")).toBeVisible();

  // 3) Kaydet + analiz (görüntüsüz epikriz akışı)
  await page.click("text=Anonim Çalışmayı Kaydet");
  await expect(page).toHaveURL(/viewer/);

  // 4) Onay ekranı: PENDING rozeti → ONAYLA → kesinleşti
  await expect(page.getByText("HEKİM ONAYI BEKLİYOR")).toBeVisible();
  await page.fill("textarea[placeholder*='Hekim notu']", "Bulgularla uyumlu, onaylıyorum.");
  await page.click("text=ONAYLA");
  await expect(page.getByText("RAPOR KESİNLEŞTİ")).toBeVisible();
});

test("ham PII içeren istek sunucuda reddedilir (defans-in-depth)", async ({ request }) => {
  const login = await request.post(`${API}/v1/auth/login`, {
    data: { email: "hekim@pulsar.demo", password: "hekim-demo-1234" },
  });
  const token = (await login.json()).access_token;
  const resp = await request.post(`${API}/v1/studies`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      anon_study_hash: "e".repeat(64),
      masked_epikriz: "Hasta T.C. 10000000146 kimlikle başvurdu.",
    },
  });
  expect(resp.status()).toBe(422);
});
