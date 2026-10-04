using System;
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
    /// <summary>Helpers para construir UI por código con un estilo consistente.</summary>
    public static class UIFactory
    {
        public static readonly Color Ink = new Color(0.07f, 0.06f, 0.08f, 0.92f);
        public static readonly Color Paper = new Color(0.96f, 0.92f, 0.82f, 1f);
        public static readonly Color Gold = new Color(1f, 0.82f, 0.38f, 1f);
        public static readonly Color Red = new Color(0.82f, 0.12f, 0.1f, 1f);
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
            var rt = Rect(name, parent, Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            return rt;
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

        public static void Outline(TextMeshProUGUI t, float width = 0.2f)
        {
            t.outlineWidth = width;
            t.outlineColor = new Color32(10, 8, 12, 255);
        }

        public static Button Button(string name, Transform parent, string label, Vector2 size, UnityAction onClick)
        {
            var bg = Image(name, parent, new Color(0.1f, 0.09f, 0.12f, 0.85f));
            bg.raycastTarget = true;
            bg.rectTransform.sizeDelta = size;
            var b = bg.gameObject.AddComponent<Button>();
            var colors = b.colors;
            colors.normalColor = new Color(1f, 1f, 1f, 0.85f);
            colors.highlightedColor = new Color(1f, 0.85f, 0.5f, 1f);
            colors.selectedColor = new Color(1f, 0.8f, 0.4f, 1f);
            colors.pressedColor = new Color(0.9f, 0.6f, 0.3f, 1f);
            colors.fadeDuration = 0.08f;
            b.colors = colors;
            b.targetGraphic = bg;
            var t = Text("Label", bg.transform, label, 34, Paper, TextAlignmentOptions.Center, true);
            var rt = t.rectTransform; rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one; rt.sizeDelta = Vector2.zero;
            b.onClick.AddListener(() => Game.Audio?.Play("ui_select", null, 0.6f));
            if (onClick != null) b.onClick.AddListener(onClick);
            bg.gameObject.AddComponent<ButtonSelectSound>();
            return b;
        }

        public static Slider Slider(string name, Transform parent, string label, float value, UnityAction<float> onChange, float width = 620f)
        {
            var row = Rect(name, parent, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(width, 64));
            var l = Text("Label", row, label, 30, Paper, TextAlignmentOptions.Left);
            l.rectTransform.anchorMin = new Vector2(0, 0); l.rectTransform.anchorMax = new Vector2(0.45f, 1); l.rectTransform.sizeDelta = Vector2.zero; l.rectTransform.anchoredPosition = Vector2.zero;
            var sgo = new GameObject("Slider", typeof(RectTransform));
            var srt = sgo.GetComponent<RectTransform>();
            srt.SetParent(row, false);
            srt.anchorMin = new Vector2(0.48f, 0.3f); srt.anchorMax = new Vector2(1f, 0.7f); srt.sizeDelta = Vector2.zero;
            var bg = Image("Background", srt, new Color(1, 1, 1, 0.15f)); bg.rectTransform.anchorMin = Vector2.zero; bg.rectTransform.anchorMax = Vector2.one; bg.rectTransform.sizeDelta = Vector2.zero;
            var fillArea = Rect("FillArea", srt, Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            var fill = Image("Fill", fillArea, Gold); fill.rectTransform.anchorMin = Vector2.zero; fill.rectTransform.anchorMax = new Vector2(0, 1); fill.rectTransform.sizeDelta = Vector2.zero;
            var handleArea = Rect("HandleArea", srt, Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            var handle = Image("Handle", handleArea, Paper); handle.rectTransform.sizeDelta = new Vector2(22, 36);
            var s = sgo.AddComponent<Slider>();
            s.fillRect = fill.rectTransform; s.handleRect = handle.rectTransform; s.targetGraphic = handle;
            s.minValue = 0f; s.maxValue = 1f; s.value = value;
            handle.raycastTarget = true; bg.raycastTarget = true;
            s.onValueChanged.AddListener(onChange);
            return s;
        }
    }

    public class ButtonSelectSound : MonoBehaviour, ISelectHandler, IPointerEnterHandler
    {
        public void OnSelect(BaseEventData e) => Game.Audio?.Play("ui_move", null, 0.35f);
        public void OnPointerEnter(PointerEventData e) => EventSystem.current?.SetSelectedGameObject(gameObject);
    }
}
