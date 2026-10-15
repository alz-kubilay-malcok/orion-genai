# LiteLLM talep formu — alias güncellemesi

LiteLLM anahtar talebinde (`litellm_api_anahtari`) formda üç değişiklik var. MCP formları aynı kalıyor.

Üretilen alias:

```text
ALZ-{DEPARTMAN}-{ORTAM}-{PROJE}-{AMAC}
ALZ-{DEPARTMAN}-BRYSL-{AD}-{PROJE}-{AMAC}    ortam = BIREYSEL
```

Kişi adı için yeni alan yok. Bireyselde mevcut `talep_eden_adi` kullanılır.

## 1. Ortam (`ortam`)

Listeye `BIREYSEL` eklenecek. Mevcut değerler duruyor: `DEV`, `STG`, `PROD`.

## 2. Kullanım amacı (`kullanim_amaci`)

Eski liste kalkıyor: `RAG`, `CHAT`, `AGENT`, `DIGERI`. Yeni liste, alias’ın son parçasıyla aynı:

| Etiket | Gönderilecek değer |
| --- | --- |
| Coder | `CODER` |
| IDP | `IDP` |
| Chatbot | `CHATBOT` |
| Agentic | `AGENTIC` |
| Kubeflow | `KUBEFLOW` |
| Other | `OTHER` |

Eski seçeneklerin karşılığı: `RAG` ve `AGENT` → `AGENTIC`, `CHAT` → `CHATBOT`, `DIGERI` → `OTHER`.

## 3. Proje (`proje_adi`)

Yeni zorunlu metin alanı. Alias’ta sadece harf ve rakam kullanılır (boşluk, tire vb. atılır), en fazla 15 karakter. Örnek: `Knime` → `KNIME`, `VS Code` → `VSCODE`. 15 karakteri aşarsa her kelimenin ilk harfi korunup kalan sesli harfler atılır: `contact center profanity` → `CNTCTCNTRPRFNTY`.

## Örnekler

- `ortam=PROD`, `proje_adi=Deepfinder`, `kullanim_amaci=AGENTIC` → `ALZ-GENAI-PROD-DEEPFINDER-AGENTIC`
- `ortam=BIREYSEL`, `talep_eden_adi=Ali Veli`, `proje_adi=Knime`, `kullanim_amaci=OTHER` → `ALZ-GENAI-BRYSL-ALI-VELI-KNIME-OTHER`

`kullanim_amaci` listesini şimdi güncelleyebilirsiniz. `proje_adi` ve `BIREYSEL` için panel tarafı hazır olunca haber vereceğiz; ondan önce bu iki değeri göndermeyin.
