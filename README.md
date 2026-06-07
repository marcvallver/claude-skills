<div align="center">

# 🧰 claude-skills

**Custom [Claude Code](https://claude.com/claude-code) skills & tooling.**

A home for reusable skills and small command-line tools I build to automate real workflows —
each one self-contained, documented, and free to use.

<p>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge"></a>
  <img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-D97757?style=for-the-badge&logo=claude&logoColor=white">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white">
</p>

<p><b>⚡ PLUGS INTO</b></p>
<p>
  <img alt="NotebookLM" src="https://img.shields.io/badge/NotebookLM-1A73E8?style=for-the-badge&logoColor=white">
  <img alt="Gemini" src="https://img.shields.io/badge/Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white">
  <img alt="Google Drive" src="https://img.shields.io/badge/Google_Drive-4285F4?style=for-the-badge&logo=googledrive&logoColor=white">
  <img alt="Claude" src="https://img.shields.io/badge/Claude-D97757?style=for-the-badge&logo=claude&logoColor=white">
</p>

<p><b>🛠️ BUILT WITH</b></p>
<p>
  <img alt="rclone" src="https://img.shields.io/badge/rclone-3F87C2?style=for-the-badge&logo=rclone&logoColor=white">
  <img alt="pandoc" src="https://img.shields.io/badge/pandoc-2C3E50?style=for-the-badge&logo=pandoc&logoColor=white">
  <img alt="Typst" src="https://img.shields.io/badge/Typst-239DAD?style=for-the-badge&logo=typst&logoColor=white">
</p>

</div>

---

## 📦 Skills

| Skill | What it does |
| --- | --- |
| [**notebooklm-sync**](skills/notebooklm-sync/) | Keep your **NotebookLM** sources in sync with a **Google Drive** folder (via rclone), converting docs + a drop-in inbox to PDF and updating them in place so NotebookLM/Gemini auto-syncs the changes. |

---

## 🚀 Using a skill

Each skill lives under [`skills/`](skills/) and ships with its own `README.md`, `SKILL.md`
(the [Claude Code skill](https://docs.claude.com/en/docs/claude-code) manifest) and any scripts it
needs. To use one:

1. **As a Claude Code skill** — copy (or symlink) the skill folder into `~/.claude/skills/` (user
   scope) or `<repo>/.claude/skills/` (project scope). Claude auto-discovers it.
2. **As a plain CLI tool** — read the skill's `README.md`; most are a single Python script you run
   directly.

```bash
# Example: install notebooklm-sync as a user-scope skill
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/notebooklm-sync" ~/.claude/skills/notebooklm-sync
```

---

## 🤝 Contributing

Each skill is independent. Open an issue or PR for bugs, ideas or new skills. Keep skills
self-contained (their own README + SKILL.md), deterministic where possible, and dependency-light.

## 📄 License

[MIT](LICENSE) © Marc Vallverdú
