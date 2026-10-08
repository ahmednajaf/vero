# Vero brand assets

Derived from the user's supplied brand board, without changing the identity. Original: `ChatGPT Image Sep 29, 2026 at 07_12_27 PM.png`.

Built-in image editing was used to separate the horizontal wordmark and app icon with transparent backgrounds. This used the supplied brand image only, not Ollama. No company reports were sent to the image tool, and no model was downloaded.

Production assets:

- `frontend/public/brand/vero-wordmark.png` — horizontal mark, used on the landing page and navigation.
- `frontend/public/brand/vero-icon.png` — supplied white/green V on charcoal, used in the collapsed rail, favicon and Apple touch icon.

Palette: charcoal `#111315`, graphite `#6B6F72`, green `#32F287`. Normal UI surfaces stay neutral; green accents mark navigation and company locations, not environmental performance.

## Image-edit prompts

Wordmark:

> Use case: background-extraction. Edit target: supplied Vero brand board. Extract ONLY the large primary horizontal Vero logo at upper left: black/charcoal V left stroke, emerald green gradient V right stroke, and black lowercase 'ero' wordmark. Preserve exactly the original letter shapes, proportions, gradient and spacing. Remove ALL background, taglines, labels, dividers and other elements. Produce a tightly framed high-resolution horizontal logo with a genuinely transparent alpha background and modest equal clear padding. Text verbatim: Vero. Do not redesign or invent details. This is a production website logo cutout from the supplied image, not a brand board.

Icon:

> Use case: background-extraction. Edit target: attached Vero brand board. Extract only the large black rounded-square app icon labelled 180x180 in the middle of the board. Preserve the exact original white left V stroke and green gradient right V stroke and their geometry, on the charcoal-black rounded square. Remove every label, every other element, and the background outside the rounded square, which must be genuinely transparent alpha. Produce a square high-resolution app icon, tightly framed with a tiny even transparent margin, suitable for favicon and Apple touch icon. No text. No redesign. Keep original V proportions, gap, corner radius, white stroke and green gradient.

## Component provenance

The existing MIT-licensed COBE globe and Manu Arora sidebar adaptations remain in use, with Vero styling. The liquid-glass material is an independent CSS/SVG implementation referencing the user-approved Suraj Gaud liquid-glass component on 21st.dev; no claim is made that its unlicensed source was copied. Backdrop blur, translucent tint, rim lighting and SVG displacement are separate layers. Reduced-transparency settings disable the material; browsers without SVG backdrop-filter support retain the CSS blur fallback.
## Sustainobot — October 2026 addition

The user supplied the robot mockup and requested no green accents. The original uploads are unchanged. The production cutout is `frontend/public/brand/sustainobot-cyan.png`, produced with the built-in image editor (not a Python image transform).

Final edit prompt: preserve the supplied friendly robot, pearl-white body, charcoal glass face, pose and proportions. Replace all green leaves, stem, chest mark, eyes and small glows with restrained ice-blue/cyan highlights (#69c9ef) and steel-blue shadows (#3387b8). Preserve the transparent background and clean edges. Remove the mockup's writing, speech bubbles, floor graphics and background; add no lettering or extra objects.

The chat presentation is adapted from the `ChatMessages` source supplied by the user on 8 October: charcoal panel, indigo/violet user bubbles, Framer Motion transitions and Lucide icons. The adaptation deliberately excludes its synthetic message list, autoplay/replay timers and canned assistant reply. Source-backed requests use the existing Vero API; the typing indicator follows actual pending requests and respects reduced motion.
