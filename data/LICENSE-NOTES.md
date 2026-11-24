# Data Licensing & Compliance Notes

> Source: Delhi Transport Stack platform (https://delhi.transportstack.in)
> Reviewed 2026-11-11 from the site **Terms of Use** and the dataset
> **License Agreement v1.0** (`LicenceAgreement1.0.pdf`, attached to each Open dataset).
> This is our internal compliance summary — **not** legal advice.

## TL;DR

The datasets are released under an **open-data style license** (attribution +
share-alike flavour). Derivatives are allowed, use abroad is allowed, and it is
compatible with producing an **open-source** hackathon deliverable — **as long as
we attribute the source, don't redistribute raw data on its own, and flag our
modifications.**

## What the license permits (Schedule 1 — Licensed Rights)

- **Recipients:** all registered users (so each teammate should register).
- **Modification:** creating derivatives is **allowed**. ✅ (our future models / aggregates)
- **Separation:** any part may be freely used, distributed, and modified; downstream
  recipients get the **same rights** (share-alike).
- **Compilation:** may be distributed alongside other distinct works without
  restricting those works.
- **Redistribution:** redistributing the licensed work **on its own is NOT allowed**,
  but it **is allowed as part of a collection from multiple sources**.
- **Term:** perpetual; 1-month notice to terminate. **No territorial restriction** (N/A).

## Our obligations

- **Attribution (mandatory):** any app / use-case built on the data or API must
  credit **"Delhi Transport Stack"** (DoT, GNCTD).
- **Integrity:** modified/derived versions must carry a **different name or version**
  or otherwise **indicate what changes were made**.
- **Data protection (clause 3.1):** implement reasonable technical & organizational
  measures to protect the data against loss / unlawful access — aligns with our ISMS duties.
- **Declared purpose:** use must stay within the purpose declared at request time
  (we are declaring **Non-Commercial Use**).
- **Non-transferable:** the license/agreement can't be transferred; it's granted to
  the registered user.
- **Notify** the publisher of any data defects; data is provided **"as is"**, no warranty.
- **Governing law:** Indian law, exclusive jurisdiction of Delhi courts.
- **Exemptions:** license does NOT cover personal info, names, logos, official
  symbols, or third-party IP (patents/trademarks).
- The publisher may **suspend access** for data tied to critical national
  infrastructure or on law-enforcement direction.

## How this maps to our repo (compliance rules)

1. **Never commit raw datasets** to the (public) repo → already enforced by
   `.gitignore` (`data/*`). Publish **code + fetch instructions**, not the raw data.
2. If we must ship sample/derived data, treat it as a **derivative**: rename/version
   it, **note the changes**, include the **attribution statement**, and keep it
   aggregated (not a verbatim redistribution of the raw dataset).
3. Put an **attribution line** in the app UI, README, and technical note, e.g.:
   > "Data source: Delhi Transport Stack (Department of Transport, GNCTD). Used under
   > the Transport Stack data License Agreement v1.0. Derived/aggregated by [team];
   > modifications noted in the technical note."
4. Each teammate should **register** on the platform (recipients = registered users).
5. Keep credentials/API keys out of git (`.env`, gitignored).

## Status

- [x] Site Terms of Use reviewed
- [x] Dataset License Agreement v1.0 reviewed
- [x] GTFS Static data request submitted + approved (2026-11-11, Non-Commercial Use) and downloaded to `data/delhi_buses_static_gtfs/`
