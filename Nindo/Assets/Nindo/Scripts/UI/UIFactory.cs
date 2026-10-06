using System;
using System.Text;
using TMPro;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.EventSystems;
using UnityEngine.UI;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem.UI;
#endif

namespace Nindo
{
    /// <summary>
    /// Helpers para construir la UI por código con el estilo "Tinta y Bandana": paneles de pincel seco,
    /// cintas de bandana para lo elegido, teclas de papel y contorno de tinta (el lenguaje del arte del equipo).
    /// </summary>
    public static class UIFactory
    {
        // ---- colores (los del arte del equipo: bandana roja, dragón dorado, papel y tinta)
        public static readonly Color Ink = new Color(0.043f, 0.039f, 0.051f, 0.9f);      // #0B0A0D
        public static readonly Color Paper = new Color(0.961f, 0.922f, 0.82f, 1f);       // #F5EBD1
        public static readonly Color PaperDim = new Color(0.78f, 0.74f, 0.66f, 1f);      // texto no elegido
        public static readonly Color Gold = new Color(1f, 0.82f, 0.376f, 1f);            // #FFD160
        public static readonly Color Red = new Color(0.824f, 0.039f, 0.067f, 1f);        // #D20A11, la bandana
        public static readonly Color Maroon = new Color(0.29f, 0.043f, 0.043f, 1f);      // #4A0B0B
        public static readonly Color Crimson = new Color(0.91f, 0.137f, 0.102f, 1f);     // #E8231A, imparable
        public static readonly Color Steel = new Color(0.65f, 0.82f, 1f, 1f);            // #A6D2FF, guardia
        public static readonly Color Jade = new Color(0.5f, 0.88f, 0.63f, 1f);           // #7FE0A0
        public static readonly Color Lacquer = new Color(0.11f, 0.102f, 0.125f, 0.94f);  // sello vacío
        public static readonly Color Panel = new Color(0.05f, 0.05f, 0.08f, 0.78f);

        static TMP_FontAsset titleFont, bodyFont;
        static Sprite white;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() { titleFont = bodyFont = null; white = null; }

        public static TMP_FontAsset TitleFont
        {
            get
            {
                if (titleFont == null)
                {
                    var c = Game.LoadContent();
                    if (c.titleFont != null)
                    {
                        try { titleFont = TMP_FontAsset.CreateFontAsset(c.titleFont); } catch (Exception e) { Debug.LogWarning("[Nindo] Fuente de títulos: " + e.Message); }
                    }
                    if (titleFont == null) titleFont = BodyFont;
                }
                return titleFont;
            }
        }

        public static TMP_FontAsset BodyFont
        {
            get
            {
                if (bodyFont == null)
                {
                    var c = Game.LoadContent();
                    if (c.bodyFont != null)
                    {
                        try { bodyFont = TMP_FontAsset.CreateFontAsset(c.bodyFont); } catch (Exception e) { Debug.LogWarning("[Nindo] Fuente de texto: " + e.Message); }
                    }
                    if (bodyFont == null) bodyFont = TMP_Settings.defaultFontAsset;
                }
                return bodyFont;
            }
        }

        public static Sprite White
        {
            get
            {
                if (white == null)
                {
                    var tex = Texture2D.whiteTexture;
                    white = Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f));
                }
                return white;
            }
        }

        public static Canvas CreateCanvas(string name, int order)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            var canvas = go.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = order;
            var scaler = go.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920, 1080);
            scaler.matchWidthOrHeight = 0.5f;
            return canvas;
        }

        /// <summary>
        /// Canvas anidado: lo que se mueve todos los cuadros (dragón, marcas sobre el mundo, diálogo) se
        /// reconstruye solo; si no, cualquier cambio rehacía la malla de toda la UI (HUD estático y paneles).
        /// </summary>
        public static Canvas Nest(RectTransform rt, bool clickable = false)
        {
            var c = rt.gameObject.AddComponent<Canvas>();
            if (clickable) rt.gameObject.AddComponent<GraphicRaycaster>();
            return c;
        }

        public static void EnsureEventSystem()
        {
            if (EventSystem.current != null) return;
            var go = new GameObject("EventSystem", typeof(EventSystem));
#if ENABLE_INPUT_SYSTEM
            go.AddComponent<InputSystemUIInputModule>();
#else
            go.AddComponent<StandaloneInputModule>();
#endif
        }

        public static RectTransform Rect(string name, Transform parent, Vector2 anchorMin, Vector2 anchorMax, Vector2 pivot, Vector2 pos, Vector2 size)
        {
            var go = new GameObject(name, typeof(RectTransform));
            var rt = go.GetComponent<RectTransform>();
            rt.SetParent(parent, false);
            rt.anchorMin = anchorMin; rt.anchorMax = anchorMax; rt.pivot = pivot;
            rt.anchoredPosition = pos; rt.sizeDelta = size;
            return rt;
        }

        public static RectTransform Stretch(string name, Transform parent)
        {
            return Rect(name, parent, Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
        }

        /// <summary>Rect con ancla y pivote en el mismo punto (lo más común para elementos sueltos).</summary>
        public static RectTransform At(string name, Transform parent, Vector2 anchor, Vector2 pos, Vector2 size)
        {
            return Rect(name, parent, anchor, anchor, anchor, pos, size);
        }

        public static Image Image(string name, Transform parent, Color c, Sprite sprite = null)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(parent, false);
            var img = go.GetComponent<Image>();
            img.sprite = sprite;
            img.color = c;
            img.raycastTarget = false;
            return img;
        }

        public static Image Image(string name, Transform parent, Color c, Vector2 anchor, Vector2 pos, Vector2 size, Sprite sprite = null)
        {
            var img = Image(name, parent, c, sprite);
            var rt = img.rectTransform;
            rt.anchorMin = rt.anchorMax = anchor; rt.pivot = anchor;
            rt.anchoredPosition = pos; rt.sizeDelta = size;
            return img;
        }

        /// <summary>Imagen con pivote en el centro (para escalar y girar en su lugar).</summary>
        public static Image Centered(string name, Transform parent, Color c, Vector2 anchor, Vector2 pos, Vector2 size, Sprite sprite)
        {
            var img = Image(name, parent, c, anchor, pos, size, sprite);
            img.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            return img;
        }

        /// <summary>
        /// Sprite de 9 partes cuyos bordes escalan con el alto: una cinta o un trazo de 120 px dibujado a 60 tiene
        /// las puntas a la mitad (con el multiplicador en 1 el nudo de la cinta salía a tamaño de textura).
        /// Si el sprite no tiene borde (falta el arte), queda simple.
        /// </summary>
        public static Image Sliced(string name, Transform parent, Sprite sprite, Color c, float height)
        {
            var img = Image(name, parent, c, sprite != null ? sprite : White);
            if (sprite != null && sprite.border.sqrMagnitude > 0f)
            {
                img.type = UnityEngine.UI.Image.Type.Sliced;
                img.pixelsPerUnitMultiplier = sprite.rect.height / Mathf.Max(1f, height);
            }
            return img;
        }

        public static TextMeshProUGUI Text(string name, Transform parent, string text, float size, Color c, TextAlignmentOptions align = TextAlignmentOptions.Center, bool title = false)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var t = go.AddComponent<TextMeshProUGUI>();
            var f = title ? TitleFont : BodyFont;
            if (f != null) t.font = f;
            t.text = text;
            t.fontSize = size;
            t.color = c;
            t.alignment = align;
            t.raycastTarget = false;
#if UNITY_2023_2_OR_NEWER
            t.textWrappingMode = TextWrappingModes.Normal;
#else
            t.enableWordWrapping = true;
#endif
            return t;
        }

        public static TextMeshProUGUI Text(string name, Transform parent, string text, float size, Color c, Vector2 anchor, Vector2 pos, Vector2 boxSize, TextAlignmentOptions align = TextAlignmentOptions.Center, bool title = false)
        {
            var t = Text(name, parent, text, size, c, align, title);
            var rt = t.rectTransform;
            rt.anchorMin = rt.anchorMax = anchor; rt.pivot = anchor;
            rt.anchoredPosition = pos; rt.sizeDelta = boxSize;
            return t;
        }

        /// <summary>En un renglón: "¡DESEQUILIBRADO!" o "Falta Espíritu" no pueden partirse sobre un enemigo.</summary>
        public static TextMeshProUGUI NoWrap(TextMeshProUGUI t)
        {
#if UNITY_2023_2_OR_NEWER
            t.textWrappingMode = TextWrappingModes.NoWrap;
#else
            t.enableWordWrapping = false;
#endif
            return t;
        }

        public static void Outline(TextMeshProUGUI t, float width = 0.2f)
        {
            // un texto creado bajo un padre inactivo (p. ej. los marcadores durante una cinemática)
            // todavía no corrió el Awake de TMP: setear el borde ahí tira NullReference adentro de TMP
            if (!t.gameObject.activeInHierarchy) { t.gameObject.AddComponent<DeferredOutline>().width = width; return; }
            ApplyOutline(t, width);
        }

        internal static void ApplyOutline(TextMeshProUGUI t, float width)
        {
            t.outlineWidth = width;   // crea la instancia de material propia del texto
            t.outlineColor = new Color32(10, 8, 12, 255);
            // TMP_SDF-Mobile solo dibuja el borde con este keyword (nada lo activa en runtime)
            t.fontSharedMaterial.EnableKeyword(ShaderUtilities.Keyword_Outline);
        }

        // ================================================================== menús
        /// <summary>
        /// Ítem de menú "Nindō": texto con pincel y kunai de cursor al elegirlo (NindoMenuItem). El rect del ítem
        /// mide 'size'.
        /// </summary>
        public static Button MenuItem(string name, Transform parent, string label, Vector2 size, UnityAction onClick, float fontSize = 38f, TextAlignmentOptions align = TextAlignmentOptions.Left)
        {
            var rt = Rect(name, parent, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, size);
            // área de clic transparente (sin ella el mouse no "entra" al ítem)
            var hit = rt.gameObject.AddComponent<Image>();
            hit.color = new Color(0, 0, 0, 0);
            var b = rt.gameObject.AddComponent<Button>();
            b.transition = Selectable.Transition.None;
            b.targetGraphic = hit;
            AttachFocus(rt, label, fontSize, align, size);
            b.onClick.AddListener(() => Game.Audio?.Play("ui_select", null, 0.6f));
            if (onClick != null) b.onClick.AddListener(onClick);
            return b;
        }

        /// <summary>Le pone a un Selectable (en 'rt') el kunai y la etiqueta de NindoMenuItem.</summary>
        public static NindoMenuItem AttachFocus(RectTransform rt, string label, float fontSize, TextAlignmentOptions align, Vector2 size, bool labelOwnsRow = true)
        {
            var item = rt.gameObject.AddComponent<NindoMenuItem>();
            var cur = Centered("Cursor", rt, Gold, new Vector2(0f, 0.5f), new Vector2(-62f, 0f), new Vector2(86f, 30f), UISprites.Kunai);
            var t = Text("Label", rt, label, fontSize, item.labelNormal, align, true);
            NoWrap(t);
            var trt = t.rectTransform;
            trt.anchorMin = Vector2.zero; trt.anchorMax = Vector2.one;
            trt.offsetMin = new Vector2(align == TextAlignmentOptions.Left ? 70f : 0f, 0f); trt.offsetMax = Vector2.zero;
            if (labelOwnsRow) Outline(t, 0.12f);
            item.cursor = cur.rectTransform; item.cursorImage = cur; item.cursorPos = new Vector2(-62f, 0f);
            item.label = t;
            item.Refresh();
            return item;
        }

        /// <summary>Fila de opción con deslizador: pista de pincel, relleno dorado, rombo rojo y el % a la derecha.</summary>
        public static Slider OptionSlider(string name, Transform parent, string label, float value, UnityAction<float> onChange, Vector2 size)
        {
            var row = Rect(name, parent, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, size);
            var hit = row.gameObject.AddComponent<Image>();
            hit.color = new Color(0, 0, 0, 0);
            var s = row.gameObject.AddComponent<Slider>();
            s.transition = Selectable.Transition.None;
            s.targetGraphic = hit;
            AttachFocus(row, label, 30f, TextAlignmentOptions.Left, size, false);
            // la pista termina antes de la caja del %: con 0.42 el rombo, al 100%, tapaba el "100%"
            float x0 = size.x * 0.5f + 10f, w = size.x * 0.36f;
            var track = Image("Track", row, new Color(Paper.r, Paper.g, Paper.b, 0.28f), new Vector2(0f, 0.5f), new Vector2(x0, 0f), new Vector2(w, 16f), UISprites.BrushLine);
            track.rectTransform.pivot = new Vector2(0f, 0.5f);
            var fillArea = Rect("FillArea", track.rectTransform, Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            var fill = Image("Fill", fillArea, Gold, UISprites.BrushLine != null ? UISprites.BrushLine : White);
            fill.rectTransform.anchorMin = Vector2.zero; fill.rectTransform.anchorMax = new Vector2(0, 1); fill.rectTransform.sizeDelta = Vector2.zero;
            var handleArea = Rect("HandleArea", track.rectTransform, Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            var handle = Image("Handle", handleArea, Red, UISprites.Pip != null ? UISprites.Pip : White);
            handle.rectTransform.sizeDelta = new Vector2(30, 30);
            var pct = Text("Value", row, "", 26, Paper, new Vector2(1f, 0.5f), new Vector2(-6f, 0f), new Vector2(90, 40), TextAlignmentOptions.Right);
            s.fillRect = fill.rectTransform; s.handleRect = handle.rectTransform;
            s.minValue = 0f; s.maxValue = 1f; s.value = value;
            pct.text = Mathf.RoundToInt(value * 100f) + "%";
            s.onValueChanged.AddListener(v => pct.text = Mathf.RoundToInt(v * 100f) + "%");
            s.onValueChanged.AddListener(onChange);
            return s;
        }

        /// <summary>Fila de opción "‹ valor ›" (izquierda/derecha la cambian).</summary>
        public static NindoSelector OptionSelector(string name, Transform parent, string label, string[] options, int index, Action<int> onChange, Vector2 size)
        {
            var row = Rect(name, parent, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, size);
            var hit = row.gameObject.AddComponent<Image>();
            hit.color = new Color(0, 0, 0, 0);
            var sel = row.gameObject.AddComponent<NindoSelector>();
            sel.transition = Selectable.Transition.None;
            sel.targetGraphic = hit;
            AttachFocus(row, label, 30f, TextAlignmentOptions.Left, size, false);
            float cx = size.x * 0.5f + 10f + size.x * 0.21f;
            var box = Rect("Value", row, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(cx, 0f), new Vector2(size.x * 0.42f, size.y));
            var v = Text("Text", box, "", 28, Paper, TextAlignmentOptions.Center, true);
            NoWrap(v);
            v.rectTransform.anchorMin = v.rectTransform.anchorMax = new Vector2(0.5f, 0.5f);
            v.rectTransform.sizeDelta = new Vector2(size.x * 0.32f, size.y);
            // flechas: kunai chicos, el de la izquierda dado vuelta
            var l = Centered("Left", box, Gold, new Vector2(0f, 0.5f), new Vector2(14f, 0f), new Vector2(46f, 16f), UISprites.Kunai);
            l.rectTransform.localRotation = Quaternion.Euler(0, 0, 180f);
            var r = Centered("Right", box, Gold, new Vector2(1f, 0.5f), new Vector2(-14f, 0f), new Vector2(46f, 16f), UISprites.Kunai);
            sel.options = options; sel.valueText = v; sel.leftArrow = l.rectTransform; sel.rightArrow = r.rectTransform;
            sel.SetIndex(index, false);
            sel.onChange = onChange;
            return sel;
        }

        // ================================================================== teclas
        /// <summary>
        /// Tecla dibujada (papel con contorno de tinta): rectangular para el teclado y los gatillos, redonda para
        /// los botones del mando, con el símbolo de su color (□ rosa, ○ rojo, △ verde, × azul; A verde, B roja...).
        /// </summary>
        public static RectTransform KeyCap(Transform parent, string glyph, float height, Vector2 anchor, Vector2 pos)
        {
            var rt = Rect("Key", parent, anchor, anchor, new Vector2(0.5f, 0.5f), pos, new Vector2(height, height));
            var bg = Image("Cap", rt, Color.white, UISprites.KeyCap);
            bg.rectTransform.anchorMin = Vector2.zero; bg.rectTransform.anchorMax = Vector2.one; bg.rectTransform.sizeDelta = Vector2.zero;
            var t = Text("Glyph", rt, "", height * 0.56f, Color.black, TextAlignmentOptions.Center, false);
            NoWrap(t);
            t.fontStyle = FontStyles.Bold;
            t.rectTransform.anchorMin = Vector2.zero; t.rectTransform.anchorMax = Vector2.one;
            t.rectTransform.offsetMin = new Vector2(2f, height * 0.12f); t.rectTransform.offsetMax = new Vector2(-2f, 0f);
            SetKeyCap(rt, glyph);
            return rt;
        }

        /// <summary>Pone el símbolo de una tecla hecha con KeyCap: forma (redonda o no), color y ancho a medida.</summary>
        public static void SetKeyCap(RectTransform key, string glyph)
        {
            var t = key.GetComponentInChildren<TextMeshProUGUI>();
            if (t == null || glyph == null || t.text == glyph) return;
            float h = key.sizeDelta.y;
            bool round = IsFaceButton(glyph);
            var cap = key.GetChild(0).GetComponent<Image>();
            cap.sprite = round ? UISprites.KeyRound : UISprites.KeyCap;
            cap.type = !round && cap.sprite != null && cap.sprite.border.sqrMagnitude > 0f ? UnityEngine.UI.Image.Type.Sliced : UnityEngine.UI.Image.Type.Simple;
            if (cap.sprite != null) cap.pixelsPerUnitMultiplier = cap.sprite.rect.height / Mathf.Max(1f, h);
            t.text = glyph;
            t.fontSize = h * (glyph.Length > 2 ? 0.4f : 0.56f);
            t.color = GlyphColor(glyph);
            // ancho a medida del texto ("Espacio", "Clic izq."), medido con la fuente: es una vez por cambio
            float w = round ? h : Mathf.Max(h, t.GetPreferredValues(glyph, 9999f, h).x + h * 0.56f);
            key.sizeDelta = new Vector2(w, h);
        }

        public static bool IsFaceButton(string g) => g == "□" || g == "○" || g == "△" || g == "×" || ((g == "A" || g == "B" || g == "X" || g == "Y") && Game.Input != null && Game.Input.GlyphFamily == 1);

        public static Color GlyphColor(string g)
        {
            switch (g)
            {
                case "□": return new Color(0.85f, 0.36f, 0.62f);
                case "○": return new Color(0.86f, 0.2f, 0.16f);
                case "△": return new Color(0.12f, 0.6f, 0.5f);
                case "×": return new Color(0.27f, 0.42f, 0.8f);
            }
            if (Game.Input != null && Game.Input.GlyphFamily == 1)
                switch (g)
                {
                    case "A": return new Color(0.27f, 0.6f, 0.18f);
                    case "B": return new Color(0.82f, 0.2f, 0.16f);
                    case "X": return new Color(0.2f, 0.42f, 0.8f);
                    case "Y": return new Color(0.82f, 0.6f, 0.08f);
                }
            return new Color(0.043f, 0.039f, 0.051f, 1f);
        }

        static readonly StringBuilder keySb = new StringBuilder(256);
        static readonly char[] KeyOpen = { '[', '{' };

        /// <summary>
        /// Resalta las teclas de un texto como fichas dentro del renglón: el símbolo en negrita y del color de su
        /// botón, con un velo claro encima (el resaltado de TMP se dibuja SOBRE las letras, por eso va translúcido).
        /// Sin sprite asset. Dos formas: "{Parry}" (una acción: se resuelve acá con la tecla del dispositivo de
        /// ahora, y quien muestra el texto lo vuelve a pasar cuando cambia Game.Input.GlyphVersion) y "[K]" (la
        /// tecla ya escrita: queda fija aunque se cambie de teclado a mando).
        /// </summary>
        public static string RichKeys(string text)
        {
            if (string.IsNullOrEmpty(text) || (text.IndexOf('[') < 0 && text.IndexOf('{') < 0)) return text;
            keySb.Length = 0;
            int i = 0;
            while (i < text.Length)
            {
                int a = text.IndexOfAny(KeyOpen, i);
                int b = a >= 0 ? text.IndexOf(text[a] == '[' ? ']' : '}', a + 1) : -1;
                if (a < 0 || b < 0 || b - a > 20) { keySb.Append(text, i, text.Length - i); break; }
                keySb.Append(text, i, a - i);
                string glyph = text.Substring(a + 1, b - a - 1);
                if (text[a] == '{')
                {
                    // lo que no es el nombre de una acción queda como estaba ("{1}" también: TryParse acepta números)
                    if (Game.Input == null || glyph.Length == 0 || !char.IsLetter(glyph[0]) || !Enum.TryParse(glyph, out Act act))
                    { keySb.Append(text, a, b - a + 1); i = b + 1; continue; }
                    glyph = Game.Input.Glyph(act);
                }
                Color gc = GlyphColor(glyph);
                // en el texto claro de los paneles el negro de la tecla de teclado no se ve: dorado
                if (gc.r + gc.g + gc.b < 0.3f) gc = Gold;
                keySb.Append("<mark=#F5EBD12E><color=#").Append(ColorUtility.ToHtmlStringRGB(gc)).Append("><b> ")
                     .Append(glyph).Append(" </b></color></mark>");
                i = b + 1;
            }
            return keySb.ToString();
        }
    }

    /// <summary>Aplica el borde de un texto recién cuando se activa (TMP ya inicializado).</summary>
    public class DeferredOutline : MonoBehaviour
    {
        public float width = 0.2f;
        void OnEnable()
        {
            var t = GetComponent<TextMeshProUGUI>();
            if (t != null) UIFactory.ApplyOutline(t, width);
            Destroy(this);
        }
    }
}
