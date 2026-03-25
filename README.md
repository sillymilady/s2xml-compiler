# S2XML Compiler

A mod compiler for The Sims 2. Write your mods as XML files, compile them into `.package` files that SimPE and the game can read.

## Download

Go to the [Releases](../../releases) page and download **S2XML_Compiler_Setup.exe**. Run it and follow the installer.

## Features

- **Compile** — Import XML resource files, compile to a `.package` file
- **Decompile** — Open any `.package`, extract every resource to editable XML
- **Diff** — Compare two packages side by side
- **Opcodes** — Searchable BHAV primitive reference

## Supported resource types

| XML tag | Resource | Purpose |
|---------|----------|---------|
| `<bhav>` | BHAV | Behaviour tree (game logic) |
| `<str>` | STR# | String tables (pie menu text) |
| `<trcn>` | TRCN | Named constants |
| `<tprp>` | TPRP | Parameter names for BHAVs |
| `<objf>` | OBJf | Object interaction slot wiring |
| `<glob>` | GLOB | Global behaviour link |
| `<objd>` | OBJD | Object definition |
| `<ttab>` | TTAB | Pie menu interaction table |
| `<ctss>` | CTSS | Catalog description strings |
| `<bcon>` | BCON | Behaviour constants |

## Building from source

The installer is built automatically by GitHub Actions on every push to `main`. See `.github/workflows/build.yml`.
