# Changelog

## 0.2.0

- ANSI escape sequences (SGR colors, OSC 8 hyperlinks) are zero-width and never split
- `strip_ansi()` and `shorten()`
- `initial_indent` / `subsequent_indent` (indent is per paragraph)
- `max_lines` / `placeholder`
- `keep_all` option for space-only breaking (Korean)
- CLI: `--keep-all`, `-i/--indent`, `-s/--subsequent-indent`, `-n/--max-lines`

## 0.1.0

- Initial release: `width`, `char_width`, `wrap`, `fill`, `truncate`, `pad`, CLI
