# Your template files

Drop real files here and BizReady serves them instead of the built-in text templates. No code changes, no restart.

## Replace an existing template

Name the file exactly like the template slug, with the extension you want learners to download:

```
content/templates/
  finance-13-week-cashflow.xlsx
  operations-quality-log.xlsx
```

Find the slug in **Admin → Content → Templates** (shown under the template name), or in `content/seed/*.json` as `"slug"`.

## Add an extra template to a module

Put any supported file inside a folder named after the module id:

```
content/templates/
  strategy/One-page-plan.docx
  marketing/Offer-canvas.pdf
  operations/Opening-checklist.pdf
  finance/Weekly-cash-sheet.xlsx
```

The learner title comes from the filename: `Opening-checklist.pdf` becomes **Opening Checklist**.

## Rules

- Supported extensions: `pdf`, `docx`, `xlsx`, `pptx`, `csv`, `md`, `txt`, `zip`, `png`, `jpg`.
- One file per slug for replacements; if two extensions share a slug, the first match wins.
- Maximum 10 MB per file.
- Only templates of **published** modules are downloadable.
- Files are scanned on every request, so changes appear on the next page load.
- Keep personal or confidential documents out of this folder; anything here is served to signed-in learners.

Built-in templates remain as a fallback: delete your file and the generated version returns.
