using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// Toda la UI del juego, construida por código (no depende de prefabs que se rompan), con el estilo
    /// "Tinta y Bandana": el HUD es solo la bandana roja (vida) y el dragón dorado (Espíritu, con el Filo de
    /// Ira en el lomo); los paneles son de pincel seco y lo elegido se marca con una cinta de bandana.
    /// Partes: HUD (UIManager.HUD.cs), marcas sobre el mundo (UIManager.World.cs), paneles (UIManager.Panels.cs).
    /// </summary>
    public partial class UIManager : MonoBehaviour
    {
        Canvas canvas;
        RectTransform root, hud, world, overlay, screen, screenFx, story, menus;

        // jefe
        RectTransform bossRoot, bossBack, bossNameRt;
        CanvasGroup bossGroup;
        /// <summary>0..1: cuánto se ve la barra del jefe (los paneles de abajo se corren para no pisarla).</summary>
        float BossBarAlpha => bossGroup != null ? bossGroup.alpha : 0f;
        Image bossFill, bossGhost, bossGlow, bossHanko;
        Image[] bossPips = new Image[0];
        TextMeshProUGUI bossName, bossSub, bossPostureLabel;
        Boss boss;
        float bossGhostValue = 1f, bossGhostHold, bossIntro, bossFlash, bossEnrage, bossShownHp, bossLastHp, bossLastPosture;
        readonly float[] bossPipPop = new float[8];

        Image fadeImage, flashImage;
        float flashT, flashDur;
        Color flashColor;
        RectTransform letterTop, letterBottom;
        float letterbox, letterboxTarget;

        /// <summary>
        /// Momentos en que el HUD y las marcas sobre el mundo no van: cinemáticas, pausa, muerte, final y
        /// diálogos. Antes solo se miraban las cinemáticas y el HUD (y "[E] Rezar en el santuario") se veía
        /// a través del final y de la pausa.
        /// </summary>
        bool HideHud => Game.InCutscene || PauseOpen || deathPanel.activeSelf || endPanel.activeSelf || DialogueOpen;

        void Awake()
        {
            Game.UI = this;
            gameObject.AddComponent<WorldMarkersLate>().ui = this;
            UIFactory.EnsureEventSystem();
            canvas = UIFactory.CreateCanvas("Nindo UI", 10);
            // Expand: siempre al menos 1920x1080 unidades; en 32:9 el "Volver" de Opciones y el del final
            // quedaban cortados abajo (las marcas sobre el mundo ya dividen por la escala del canvas)
            canvas.GetComponent<CanvasScaler>().screenMatchMode = CanvasScaler.ScreenMatchMode.Expand;
            canvas.transform.SetParent(transform, false);
            root = (RectTransform)canvas.transform;
            // canvas anidados: lo que se mueve cada cuadro se reconstruye solo (ver UIFactory.Nest)
            world = UIFactory.Stretch("World", root); UIFactory.Nest(world);
            hud = UIFactory.Stretch("HUD", root);
            hudGroup = hud.gameObject.AddComponent<CanvasGroup>();
            overlay = UIFactory.Stretch("Overlay", root);
            // orden: barras de cine, destello y fundido, y ENCIMA del fundido los títulos, diálogos y menús
            // (el prólogo escribe sobre negro y la muerte deja "Caíste" mientras se funde)
            screen = UIFactory.Stretch("Letterbox", overlay); UIFactory.Nest(screen);
            screenFx = UIFactory.Stretch("ScreenFX", overlay); UIFactory.Nest(screenFx);
            story = UIFactory.Stretch("Story", overlay); UIFactory.Nest(story);
            menus = UIFactory.Stretch("Menus", overlay); UIFactory.Nest(menus, true);
            BuildHUD();
            BuildBossBar();
            BuildWorldMarkers();
            BuildOverlay();
            BuildPanels();
        }

        void OnDestroy() { if (Game.UI == this) Game.UI = null; }

        // ================================================================== jefe
        // Trazo de tinta abajo: sello rojo con las katanas, nombre y título en el mismo renglón, vida en carmesí con
        // estela de papel y, a la derecha, la POSTURA en rombos (antes no se veía: contra un jefe no había forma de
        // saber cuánto faltaba para quebrarlo).
        void BuildBossBar()
        {
            bossRoot = UIFactory.Rect("BossBar", hud, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0, 40), new Vector2(1400, 150));
            UIFactory.Nest(bossRoot);
            bossGroup = bossRoot.gameObject.AddComponent<CanvasGroup>();
            bossGroup.alpha = 0f;
            bossGlow = UIFactory.Sliced("Glow", bossRoot, UISprites.BossBarBack, new Color(1f, 0.8f, 0.35f, 0f), 76f);
            Place(bossGlow.rectTransform, new Vector2(0f, 0f), new Vector2(-10f, -10f), new Vector2(1420, 76));
            var back = UIFactory.Sliced("Back", bossRoot, UISprites.BossBarBack, Color.white, 56f);
            bossBack = back.rectTransform;
            Place(bossBack, new Vector2(0f, 0f), Vector2.zero, new Vector2(1400, 56));
            bossGhost = BarFill("Ghost", bossBack, new Color(UIFactory.Paper.r, UIFactory.Paper.g, UIFactory.Paper.b, 0.85f));
            bossFill = BarFill("Fill", bossBack, BossRed);
            bossHanko = UIFactory.Centered("Hanko", bossRoot, Color.white, new Vector2(0f, 0f), new Vector2(30f, 92f), new Vector2(72, 72), UISprites.Hanko("IconBoss"));
            bossHanko.rectTransform.localRotation = Quaternion.Euler(0, 0, -5f);
            bossName = UIFactory.Text("Name", bossRoot, "", 58, UIFactory.Paper, new Vector2(0f, 0f), new Vector2(84f, 62f), new Vector2(820, 70), TextAlignmentOptions.BottomLeft, true);
            UIFactory.NoWrap(bossName);
            UIFactory.Outline(bossName, 0.2f);
            bossNameRt = bossName.rectTransform;
            bossSub = UIFactory.Text("Sub", bossRoot, "", 28, UIFactory.Gold, new Vector2(0f, 0f), new Vector2(300f, 70f), new Vector2(700, 40), TextAlignmentOptions.BottomLeft);
            UIFactory.NoWrap(bossSub);
            UIFactory.Outline(bossSub, 0.18f);
            bossPostureLabel = UIFactory.Text("Postura", bossRoot, "Postura", 22, new Color(0.86f, 0.82f, 0.74f), new Vector2(1f, 0f), new Vector2(-200f, 70f), new Vector2(160, 30), TextAlignmentOptions.BottomRight);
            UIFactory.Outline(bossPostureLabel, 0.18f);
        }

        static readonly Color BossRed = new Color(0.77f, 0.086f, 0.078f);   // (196,22,20)

        static void Place(RectTransform rt, Vector2 anchor, Vector2 pos, Vector2 size)
        {
            rt.anchorMin = rt.anchorMax = anchor; rt.pivot = anchor;
            rt.anchoredPosition = pos; rt.sizeDelta = size;
        }

        Image BarFill(string name, RectTransform parent, Color c)
        {
            var img = UIFactory.Image(name, parent, c, UISprites.BossBarFill != null ? UISprites.BossBarFill : UIFactory.White);
            img.type = Image.Type.Filled; img.fillMethod = Image.FillMethod.Horizontal; img.fillOrigin = 0;
            // adentro del trazo: el borde seco del pincel queda a la vista
            img.rectTransform.anchorMin = Vector2.zero; img.rectTransform.anchorMax = Vector2.one;
            img.rectTransform.offsetMin = new Vector2(20f, 11f); img.rectTransform.offsetMax = new Vector2(-20f, -11f);
            return img;
        }

        public void ShowBossBar(Boss b)
        {
            boss = b; bossGhostValue = 0f; bossGhostHold = 0f; bossIntro = 0f; bossEnrage = 0f; bossFlash = 0f; bossShownHp = 0f; bossLastHp = b.Health01;
            bossLastPosture = b.Imbalance;
            bossName.text = b.title;
            bossSub.text = b.subtitle;
            bossSub.color = UIFactory.Gold;
            // el título va en el mismo renglón, pegado al nombre
            float nameW = bossName.GetPreferredValues(b.title, 9999f, 70f).x;
            bossSub.rectTransform.anchoredPosition = new Vector2(84f + nameW + 18f, 70f);
            // rombos de postura: uno por punto de desequilibrio del jefe (4 o 5)
            int n = Mathf.Clamp(b.config.maxImbalance, 1, bossPipPop.Length);
            if (bossPips.Length != n)
            {
                foreach (var p in bossPips) if (p != null) Destroy(p.gameObject);
                bossPips = new Image[n];
                for (int i = 0; i < n; i++)
                {
                    bossPips[i] = UIFactory.Centered("Pip" + i, bossRoot, PipEmpty, new Vector2(1f, 0f), new Vector2(-22f - (n - 1 - i) * 30f, 84f), new Vector2(26, 26), UISprites.Pip);
                }
                bossPostureLabel.rectTransform.anchoredPosition = new Vector2(-22f - n * 30f - 4f, 70f);
            }
        }

        public void HideBossBar() => boss = null;

        /// <summary>El jefe se enfurece (cambio de fase): la barra destella, el título cambia a "¡Enfurecido!" y el nombre tiembla.</summary>
        public void BossEnraged(Boss b)
        {
            if (b == null || b != boss) return;
            bossEnrage = 2f;
            bossFlash = 1f;
            bossSub.text = "¡Enfurecido!";
            bossSub.color = UIFactory.Crimson;
        }

        static readonly Color PipEmpty = new Color(0.27f, 0.26f, 0.29f, 1f);

        void UpdateBossBar(float dt)
        {
            bool show = boss != null && boss.IsAlive && !HideHud;
            bossGroup.SetAlpha(Mathf.MoveTowards(bossGroup.alpha, show ? 1f : 0f, dt * 3f));
            if (boss == null) return;
            float t = Time.unscaledTime;
            // entrada: el trazo se pinta de izquierda a derecha y después la vida "se vierte"
            bossIntro += dt;
            float wipe = UIAnim.OutCubic(bossIntro / 0.4f);
            bossBack.SetSize(new Vector2(Mathf.Lerp(120f, 1400f, wipe), 56f));
            float hp = boss.Health01;
            float pour = Mathf.Clamp01((bossIntro - 0.35f) / 0.6f);
            // lo que se perdió queda en papel medio segundo y después se vacía despacio
            if (hp < bossLastHp - 0.0001f) { bossGhostValue = Mathf.Max(bossGhostValue, bossShownHp); bossGhostHold = 0.5f; }
            bossLastHp = hp;
            bossShownHp = pour < 1f ? Mathf.Min(hp, UIAnim.OutCubic(pour)) : Mathf.MoveTowards(bossShownHp, hp, dt * 2f);
            bossGhostHold -= dt;
            if (bossGhostHold <= 0f || pour < 1f) bossGhostValue = Mathf.MoveTowards(bossGhostValue, bossShownHp, pour < 1f ? 9f : dt * 0.35f);
            if (bossGhostValue < bossShownHp) bossGhostValue = bossShownHp;
            bossFill.fillAmount = bossShownHp;
            bossGhost.fillAmount = bossGhostValue;

            // destello del cambio de fase / del golpe fuerte
            bossFlash = Mathf.MoveTowards(bossFlash, 0f, dt * 2.5f);
            bossFill.color = Color.Lerp(BossRed, Color.white, bossFlash * bossFlash);
            if (bossEnrage > 0f)
            {
                bossEnrage -= dt;
                float shake = Mathf.Clamp01(bossEnrage - 1.6f) / 0.4f;
                bossNameRt.anchoredPosition = new Vector2(84f, 62f) + new Vector2(Mathf.Sin(t * 70f), Mathf.Cos(t * 53f)) * 4f * shake;
                if (bossEnrage <= 0f) { bossSub.text = boss.subtitle; bossSub.color = UIFactory.Gold; bossNameRt.anchoredPosition = new Vector2(84f, 62f); }
            }

            // postura: cada rombo se llena (también de a fracciones: guardia imperfecta, golpes a la guardia);
            // el que se completa salta. Agotado: titilan dorado y blanco y el trazo se enciende
            float imb = boss.Imbalance;
            bool exhausted = boss.IsExhausted;
            for (int i = 0; i < bossPips.Length; i++)
            {
                float f = Mathf.Clamp01(imb - i);
                if (f >= 0.99f && Mathf.Clamp01(bossLastPosture - i) < 0.99f) bossPipPop[i] = 1f;
                bossPipPop[i] = Mathf.MoveTowards(bossPipPop[i], 0f, dt / 0.15f);
                Color c = f >= 0.99f ? UIFactory.Gold : Color.Lerp(PipEmpty, UIFactory.Gold, f * 0.55f);
                if (exhausted) c = Color.Lerp(UIFactory.Gold, Color.white, 0.5f + 0.5f * Mathf.Sin(t * 16f));
                bossPips[i].color = c;
                bossPips[i].rectTransform.SetScale(1f + 0.4f * bossPipPop[i]);
            }
            bossLastPosture = imb;
            var gc = bossGlow.color;
            gc.a = Mathf.MoveTowards(gc.a, exhausted ? 0.55f + 0.35f * Mathf.Sin(t * 8f) : 0f, dt * 4f);
            bossGlow.color = gc;
        }

        // ================================================================== overlay (letterbox, destello, fundido)
        void BuildOverlay()
        {
            letterTop = UIFactory.Image("LetterTop", screen, Color.black).rectTransform;
            letterTop.anchorMin = new Vector2(0, 1); letterTop.anchorMax = new Vector2(1, 1); letterTop.pivot = new Vector2(0.5f, 1); letterTop.sizeDelta = new Vector2(0, 0);
            letterBottom = UIFactory.Image("LetterBottom", screen, Color.black).rectTransform;
            letterBottom.anchorMin = new Vector2(0, 0); letterBottom.anchorMax = new Vector2(1, 0); letterBottom.pivot = new Vector2(0.5f, 0); letterBottom.sizeDelta = new Vector2(0, 0);
            flashImage = UIFactory.Image("Flash", screenFx, new Color(1, 1, 1, 0));
            flashImage.rectTransform.Fill(Vector2.zero, Vector2.zero);
            fadeImage = UIFactory.Image("Fade", screenFx, new Color(0, 0, 0, 0));
            fadeImage.rectTransform.Fill(Vector2.zero, Vector2.zero);
        }

        public void ScreenFlash(Color c, float duration)
        {
            flashColor = c; flashDur = Mathf.Max(0.01f, duration); flashT = 0f;
        }

        public void Letterbox(bool on) => letterboxTarget = on ? 1f : 0f;

        public void SetFade(float alpha)
        {
            fadeImage.color = new Color(0, 0, 0, alpha);
            fadeImage.enabled = alpha > 0.001f;
        }

        public IEnumerator Fade(float to, float duration)
        {
            float from = fadeImage.color.a;
            float t = 0f;
            while (t < duration)
            {
                t += Time.unscaledDeltaTime;
                SetFade(Mathf.Lerp(from, to, Mathf.SmoothStep(0f, 1f, t / duration)));
                yield return null;
            }
            SetFade(to);
        }

        void UpdateOverlay(float dt)
        {
            if (flashT < flashDur)
            {
                flashT += dt;
                float k = Mathf.Clamp01(flashT / flashDur);
                var fc = flashColor; fc.a *= 1f - k; flashImage.color = fc;
                flashImage.enabled = fc.a > 0.001f;
            }
            else if (flashImage.enabled) flashImage.enabled = false;
            if (!Mathf.Approximately(letterbox, letterboxTarget))
            {
                letterbox = Mathf.MoveTowards(letterbox, letterboxTarget, dt * 2.5f);
                float h = 120f * Mathf.SmoothStep(0f, 1f, letterbox);
                letterTop.sizeDelta = new Vector2(0, h);
                letterBottom.sizeDelta = new Vector2(0, h);
            }
        }

        void Update()
        {
            float dt = Time.unscaledDeltaTime;
            UpdateHUD(dt);
            UpdateBossBar(dt);
            UpdateOverlay(dt);
            UpdatePanels(dt);
        }
    }

    static class RectExt
    {
        // solo si cambia: asignar el mismo valor igual marca sucio el canvas y se rehacía la malla cada cuadro
        public static void SetAlpha(this CanvasGroup g, float a) { if (g.alpha != a) g.alpha = a; }
        public static void SetPos(this RectTransform rt, Vector2 p) { if (rt.anchoredPosition != p) rt.anchoredPosition = p; }
        public static void SetSize(this RectTransform rt, Vector2 s) { if (rt.sizeDelta != s) rt.sizeDelta = s; }
        public static void SetScale(this Transform t, float s) { var v = new Vector3(s, s, s); if (t.localScale != v) t.localScale = v; }

        public static void Fill(this RectTransform rt, Vector2 offsetMin, Vector2 offsetMax)
        {
            rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one; rt.pivot = new Vector2(0.5f, 0.5f);
            rt.offsetMin = offsetMin; rt.offsetMax = offsetMax;
        }
    }
}
