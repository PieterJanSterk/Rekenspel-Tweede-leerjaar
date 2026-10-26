# Translating the game

Everything the player reads comes from one small text file per language in the
`lang/` folder (`lang/nl.json`, `lang/en.json`, ...). Adding a language means
adding one file - no programming. Once the file exists, the language appears on
the language button (top-right of the first screen) by itself.

## The short version

```
python check_translation.py --init es Español   # makes lang/es.json from the English file
# ...translate the values in lang/es.json...
python check_translation.py es                  # lists mistakes (exit code 0 = good)
python main.py                                  # click the language button to look at it
```

`--init` gives you a file that is already valid: every text is still English, so
you can translate a little at a time and the game never breaks (a text you have
not translated yet simply shows in English).

**Already installed a packaged game** (the `.exe` / `.app` / Linux program)? You
do not have to rebuild anything: put your file in a folder named `lang` **next to
the program** (next to `settings.json`) and start the game. A file with the same
code as a built-in language (say `nl.json`) replaces that language - handy for
improving a translation.

## What the file looks like

```json
{
  "_language_name": "Español",
  "_help": "...",
  "choice.start": "Empezar",
  "hud.round": "Ronda {n} / {total}",
  "board.empty": "Todavía no hay resultados para esta selección."
}
```

* **Translate the values only** - the text on the right. Never change the keys
  on the left (`"choice.start"`).
* `_language_name` is what the language button shows. Write it **in that
  language** ("Español", "Deutsch", "Nederlands"), so people can find theirs.
* **Keep the `{placeholders}`** exactly as they are (`{n}`, `{total}`, `{value}`,
  `{name}`, ...). The game fills them in: `"Ronde {n} / {total}"` becomes
  "Ronde 3 / 10". You may move them around in the sentence, but not rename or
  drop them. The checker tells you if you did.
* The file must be valid JSON and saved as **UTF-8** (accents work fine).

## Where the texts show up

| Keys start with | Where |
|---|---|
| `choice.*`, `som.*`, `theme.*`, `game.*` | the first screen: title, buttons, the four game tiles, the exercise kinds |
| `hud.*` | inside the games: scores, "Round 3 / 10", "Pairs", "Turns" |
| `name.*`, `common.done` | the screen where children type their name (on-screen keyboard) |
| `board.*` | the scoreboard: tabs, columns, the management screen, the exercise filter |
| `exercise.*` | the Plus and minus chips (see below) |
| `symbol.*` | the multiplication and division signs used in the exercises |

### Things worth knowing

* **Length.** Buttons are sized to fit their words, and the layout has been tested
  with texts about **30% longer than English**. A language with much longer words
  may need shorter wording on a few buttons.
* **`symbol.times` / `symbol.divide`.** The signs shown in the sums: Dutch uses `x`
  and `:`, English `×` and `÷`. Use what children in your country see at school.
* **The abbreviations on the Plus and minus chips** (`exercise.token.*`). The
  exercise types are named after the Dutch teaching terms: **E** = eenheid (a
  single digit), **T** = tiental (a pure ten), **TE** = tiental + eenheid (like
  47), **ZB** = zonder brug (no bridge over the ten), **MB** = met brug (with a
  bridge). Replace each by the abbreviation your teachers use; the chips
  `TE + E / MB` then show as, for example, `TU + U / WB`. Keep them short (1-3
  letters). The English file uses U (units), T (tens), TU, NB (no bridge) and
  WB (with bridge) - change them if your curriculum says otherwise.
* **`exercise.group`** is the heading above each group of chips: "Up to {n}".
* **Saved scores are language-independent.** Changing language never changes or
  loses scores or settings.
* **Letters.** The game uses the system's Arial-like font, which covers all
  Latin-script languages (accents included). Languages that need other scripts
  (Chinese, Arabic, Hindi, ...) are not supported yet.

## Handing it to an AI assistant

Copy this into any AI assistant, and paste the contents of `lang/en.json` where
it says so:

> I am translating a children's maths-practice game into **[LANGUAGE]** for
> **[AGE / COUNTRY - e.g. 7-year-olds in Spain]**. Below is the English language
> file (JSON). Produce the same JSON with all values translated into [LANGUAGE].
> Rules: keep every key unchanged; keep every `{placeholder}` exactly as written;
> set `"_language_name"` to the language's own name; keep buttons and labels
> short (not much longer than the English); use the wording a primary-school
> teacher in that country would use. Use the usual school maths signs for
> multiplication and division in `symbol.times` and `symbol.divide`. For the
> `exercise.token.*` keys give the abbreviations that school uses for
> units / tens / tens+units / without bridging the ten / with bridging the ten
> (1-3 letters each) - if there is no common abbreviation, invent short ones.
> Return only the JSON.
>
> [paste lang/en.json here]

Save the answer as `lang/<code>.json` (two-letter code, e.g. `es`), then run
`python check_translation.py <code>` and look at the game. **Please have a native
speaker or a teacher read it through** - the checker finds technical mistakes,
not awkward wording.

## Sharing your translation

If you use the project on GitHub, send the file as a pull request:
`lang/<code>.json` is all that is needed. Run `python run_tests.py` first - it
checks every language file.
