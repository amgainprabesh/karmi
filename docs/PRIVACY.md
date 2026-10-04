# Privacy — Karmi (कर्मी)

*This page is written for the homeowner, not for programmers.*

**The short version:** your naksa drawing and your home's photos stay on **your own
computer**. Karmi has no server to send them to, asks you to create no account, and
does not collect anything automatically. Everything Karmi makes — the comparison
report, the extracted models, the 3D view — is saved in a folder on your machine, and
you can delete it whenever you want.

---

## What Karmi keeps on your computer

When you run Karmi on a drawing and some photos, it creates one *run folder* (by
default `runs/<name>/`) containing:

* the drawing and photos you gave it (as copied into the run folder),
* machine-readable models it built from them (`scene.json`, `observed.json`),
* your report — `report.html`, `report.md` (Nepali and English) — and the `view.json`
  used by the 3D transition,
* a small `run.json` record of what was compared, so the result can be reproduced.

All of this is ordinary files on your disk. Nothing about them is secret from you, and
nothing about them is shared by Karmi.

**Worth knowing:** if you keep the Karmi folder inside a cloud-synced directory
(OneDrive, Google Drive, Dropbox), then your operating system will sync those files —
because that is what those programs do. If you want the data to stay purely local,
keep the run folder somewhere that is not synced.

## What never leaves your computer

By default, **none** of the following leaves your machine:

* your drawing and your photos,
* the text Karmi reads out of them (owner name, address, engineer's name and phone
  number, ward/kitta numbers),
* the report and everything derived from it,
* anything about how you use the program — there is **no telemetry**, no analytics,
  no crash reporting, no "phone home", not even a check for updates.

Karmi works fully offline. The AI models it is designed around are open-weight models
that run on your own computer; there is no company's cloud in the default path.

## If you ever choose to contribute to the dataset

Karmi hopes to publish the first open dataset of Nepali naksa drawings paired with
construction photos — it is what will make the tool work well on real Nepali drawings
for everyone. A contribution is:

* **Opt-in, explicit, and per contributor.** Nothing is collected automatically,
  ever. If you say no, the tool works exactly the same and nothing changes for you.
* **De-identified before anything is shared.** Concretely, before any file enters a
  dataset release:
  * GPS location and camera metadata (EXIF) are removed from every photo, verified
    so that the pixels themselves are untouched;
  * names, phone numbers, engineer names and NEC numbers, and ward/plot/kitta numbers
    are found and redacted from the text inside drawings;
  * files are renamed to opaque IDs — the original filenames (which often contain a
    name) are not published.
  * **Honestly:** a drawing's layout and handwriting style can still hint at who
    prepared it, and a photo of a home can still identify that home. That is why
    photos are a separate, more restrictive choice than drawings — and why you should
    only contribute what you are comfortable making public forever.
* **Revocable.** You can ask for your contribution to be withdrawn; we will remove it
  from future versions of the dataset and from our own copies. **The one honest
  caveat:** if someone already downloaded an earlier version, we cannot reach into
  their copy — open data is like that, so decide before you share.
* **No faces.** Photos that show people are excluded from a release unless there is a
  separate agreement and the people are made unidentifiable.

The dataset does not exist yet. When it does, this page and the project README will
say exactly what a contribution involves, and the decision will be yours, file by
file.

## How long does Karmi keep things?

* **Run folders stay until you delete them.** Nothing expires on its own and nothing
  is uploaded anywhere, so there is no "retention policy" other than your own
  housekeeping.
* **To delete everything for a project:** delete its run folder. That removes the
  copies of the drawing, the photos, the models and the report.
* **Suggestion:** when a project is finished, keep the report if you need it and
  delete the photos/drawings you no longer need. Remember that the report itself can
  contain your name and ward/kitta — treat it like a private document, not a
  screenshot to post in a group chat.
* **Before giving away or selling the computer:** delete the runs folder first.

## What Karmi will not do

* No accounts, no sign-ups, no passwords to lose.
* No selling data, no advertising, no tracking of any kind.
* No sending your files to any company's AI service.
* No automatic complaints or filings with any office or authority.
* No "you violated the rules" claims. Karmi only lists things *to verify* with your
  engineer or municipality — the decision is always human.

## A note about what Karmi is

Karmi is a helper, not a legal authority. It compares the approved drawing with what
it can see in photos and lists the differences worth checking; it cannot replace your
engineer's judgement, and the municipality's decision always comes first. Keep your
original approved naksa safe — Karmi does not replace it.

## नेपालीमा (सारांश)

* Karmi ले तपाईंको नक्सा र घरका फोटोहरू **तपाईंकै कम्प्युटरमा** राख्छ — तपाईं आफैं
  राजी नहुन्जेल कहीँ पनि पठाउँदैन।
* कुनै खाता (account) खोल्नु पर्दैन; कुनै जानकारी स्वतः संकलन गरिँदैन (कुनै
  telemetry छैन)। Karmi इन्टरनेट नभए पनि चल्छ।
* रिपोर्ट र सबै फाइलहरू तपाईंको आफ्नै फोल्डर (`runs/…`) मा बन्छन्। त्यो फोल्डर
  मेटाउनुभयो भने सबै मेटिन्छ।
* तपाईंको फोल्डर OneDrive/Google Drive जस्ता सिंक हुने ठाउँमा राख्नुभयो भने
  ती कम्पनीहरूले आफ्नै नियमअनुसार सिंक गर्छन् — पूर्ण रूपमा स्थानीय राख्न चाहनुहुन्छ
  भने सिंक नहुने फोल्डर प्रयोग गर्नुहोस्।
* डेटासेटमा सहयोग गर्ने निर्णय **पूर्ण रूपमा तपाईंको हो**: स्पष्ट अनुमति भए मात्र,
  फोटोका GPS/EXIF हटाएर, नाम–फोन–इन्जिनियर–वडा/कित्ता नम्बर हटाएर मात्र राखिन्छ।
  तपाईंले कुनै बेला पनि आफ्नो योगदान फिर्ता लिन सक्नुहुन्छ (पहिले नै डाउनलोड भइसकेका
  प्रतिहरू फिर्ता गर्न नसकिने कुरा इमानदारीसाथ भनिएको छ)।
* Karmi ले कसैलाई "दोषी" भन्दैन — जाँच गर्नुपर्ने सूची मात्र दिन्छ। अन्तिम निर्णय
  तपाईं र तपाईंको इन्जिनियरको हो।

## For the technical reader

The primitives behind the promises above live in `core/validate.py`:
`strip_exif()` (container-level EXIF/GPS removal, pixel data bit-for-bit unchanged),
`find_pii_candidates()` + `redact()` (Nepali phone/email/engineer/NEC/ward/kitta
heuristics), `safe_filename()` / `safe_join()` (upload path safety) and
`sanitize_model_text()` (renderer safety). The full threat model — including what is
still a requirement on other modules — is in `docs/SECURITY.md`.