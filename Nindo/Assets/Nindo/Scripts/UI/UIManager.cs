using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// Toda la UI del juego, construida por código (no depende de prefabs que se rompan).
    /// HUD con el arte del equipo: la vida es la bandana roja y el Espíritu es el dragón dorado.
    /// </summary>
    public partial class UIManager : MonoBehaviour
    {
        Canvas canvas;
        RectTransform root, hud, world, overlay;

        // HUD: campos y lógica en UIManager.HUD.cs

        // jefe
        CanvasGroup bossGroup;
        Image bossFill, bossGhost;
        Image[] bossPosture;   // mitades izquierda y derecha: se llenan desde el centro
        TextMeshProUGUI bossName, bossSub;
        Boss boss;
        float bossGhostValue = 1f;

        // marcadores en mundo
        class EnemyWidget
        {
            public RectTransform rt;
            public Image hp, hpBg;
            public Image[] pips;
            public TextMeshProUGUI status;
            public Enemy enemy;
            public float visibleUntil;
        }
        readonly List<EnemyWidget> widgets = new List<EnemyWidget>();
        readonly Dictionary<Enemy, EnemyWidget> widgetOf = new Dictionary<Enemy, EnemyWidget>();
        RectTransform lockReticle;
        Enemy lockTarget;
        TextMeshProUGUI finisherPrompt;
        TextMeshProUGUI interactPrompt;
        Interactable interactTarget;

        class Marker { public RectTransform rt; public TextMeshProUGUI text; public Image icon; public Enemy e; public float t, life; public Vector3 offset; }
        readonly List<Marker> markers = new List<Marker>();

        Image fadeImage, flashImage;
        float flashT, flashDur;
        Color flashColor;
        RectTransform letterTop, letterBottom;
        float letterbox, letterboxTarget;

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
            world = UIFactory.Stretch("World", root);
            hud = UIFactory.Stretch("HUD", root);
            hudGroup = hud.gameObject.AddComponent<CanvasGroup>();
            overlay = UIFactory.Stretch("Overlay", root);
            BuildHUD();
            BuildBossBar();
            BuildWorldMarkers();
            BuildOverlay();
            BuildPanels();
        }

        void OnDestroy() { if (Game.UI == this) Game.UI = null; }

        // ================================================================== jefe
        void BuildBossBar()
        {
            var r = UIFactory.Rect("BossBar", hud, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 56), new Vector2(1100, 110));
            bossGroup = r.gameObject.AddComponent<CanvasGroup>();
            bossGroup.alpha = 0f;
            bossName = UIFactory.Text("Name", r, "", 44, UIFactory.Paper, new Vector2(0, 1), new Vector2(0, 0), new Vector2(700, 56), TextAlignmentOptions.BottomLeft, true);
            UIFactory.Outline(bossName);
            bossSub = UIFactory.Text("Sub", r, "", 24, UIFactory.Gold, new Vector2(1, 1), new Vector2(0, -4), new Vector2(600, 40), TextAlignmentOptions.BottomRight);
            UIFactory.Outline(bossSub, 0.15f);
            var back = UIFactory.Image("Back", r, new Color(0.05f, 0.03f, 0.03f, 0.9f), new Vector2(0.5f, 0.5f), new Vector2(0, -10), new Vector2(1100, 26));
            bossGhost = UIFactory.Image("Ghost", back.transform, new Color(1f, 0.9f, 0.75f, 0.8f), UIFactory.White);
            bossGhost.type = Image.Type.Filled; bossGhost.fillMethod = Image.FillMethod.Horizontal; bossGhost.rectTransform.Fill(new Vector2(3, 3), new Vector2(-3, -3));
            bossFill = UIFactory.Image("Fill", back.transform, new Color(0.75f, 0.1f, 0.08f), UIFactory.White);
            bossFill.type = Image.Type.Filled; bossFill.fillMethod = Image.FillMethod.Horizontal; bossFill.rectTransform.Fill(new Vector2(3, 3), new Vector2(-3, -3));
            // postura del jefe bajo la vida: cada parry (y cada golpe a su guardia) la llena desde el centro; llena, se
            // quiebra y queda agotado. Los jefes no tienen las marcas de los comunes y no había forma de saber cuánto faltaba
            var pb = UIFactory.Image("PostureBack", r, new Color(0.05f, 0.03f, 0.03f, 0.8f), new Vector2(0.5f, 0.5f), new Vector2(0, -34), new Vector2(520, 10));
            bossPosture = new Image[2];
            for (int i = 0; i < 2; i++)
            {
                var img = UIFactory.Image(i == 0 ? "PostureL" : "PostureR", pb.transform, UIFactory.Gold, UIFactory.White);
                img.type = Image.Type.Filled; img.fillMethod = Image.FillMethod.Horizontal;
                img.fillOrigin = (int)(i == 0 ? Image.OriginHorizontal.Right : Image.OriginHorizontal.Left);
                img.fillAmount = 0f;
                var rt = img.rectTransform;
                rt.anchorMin = new Vector2(i == 0 ? 0f : 0.5f, 0f); rt.anchorMax = new Vector2(i == 0 ? 0.5f : 1f, 1f);
                rt.offsetMin = new Vector2(i == 0 ? 2f : 0f, 2f); rt.offsetMax = new Vector2(i == 0 ? 0f : -2f, -2f);
                bossPosture[i] = img;
            }
        }

        public void ShowBossBar(Boss b)
        {
            boss = b; bossGhostValue = 1f;
            foreach (var img in bossPosture) img.fillAmount = b.Posture01;
            bossName.text = b.title;
            bossSub.text = b.subtitle;
        }

        public void HideBossBar() => boss = null;

        void UpdateBossBar(float dt)
        {
            bool show = boss != null && boss.IsAlive && !Game.InCutscene;
            bossGroup.alpha = Mathf.MoveTowards(bossGroup.alpha, show ? 1f : 0f, dt * 2f);
            if (boss == null) return;
            float hp = boss.Health01;
            bossFill.fillAmount = Mathf.MoveTowards(bossFill.fillAmount, hp, dt * 2f);
            if (hp < bossGhostValue) bossGhostValue = Mathf.MoveTowards(bossGhostValue, hp, dt * 0.3f); else bossGhostValue = hp;
            bossGhost.fillAmount = bossGhostValue;
            bossFill.color = boss.IsExhausted ? Color.Lerp(new Color(0.75f, 0.1f, 0.08f), UIFactory.Gold, 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 8f)) : new Color(0.75f, 0.1f, 0.08f);
            float posture = boss.Posture01;
            float fill = Mathf.MoveTowards(bossPosture[0].fillAmount, posture, dt * 3f);
            // ámbar apagado que se enciende a dorado al llenarse; agotado, late dorado y blanco
            Color pc = boss.IsExhausted ? Color.Lerp(UIFactory.Gold, Color.white, 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 12f))
                : Color.Lerp(new Color(0.7f, 0.5f, 0.22f), UIFactory.Gold, posture);
            foreach (var img in bossPosture) { img.fillAmount = fill; img.color = pc; }
        }

        // ================================================================== marcadores
        void BuildWorldMarkers()
        {
            lockReticle = UIFactory.Image("Lock", world, UIFactory.Gold, new Vector2(0, 0), Vector2.zero, new Vector2(46, 46)).rectTransform;
            lockReticle.pivot = new Vector2(0.5f, 0.5f);
            lockReticle.localRotation = Quaternion.Euler(0, 0, 45);
            var inner = UIFactory.Image("Inner", lockReticle, new Color(0.1f, 0.05f, 0.02f, 0.9f));
            inner.rectTransform.Fill(new Vector2(7, 7), new Vector2(-7, -7));
            lockReticle.gameObject.SetActive(false);

            finisherPrompt = UIFactory.Text("Finisher", world, "", 30, UIFactory.Gold, new Vector2(0, 0), Vector2.zero, new Vector2(420, 60), TextAlignmentOptions.Center, true);
            finisherPrompt.rectTransform.pivot = new Vector2(0.5f, 0.5f);
#if UNITY_2023_2_OR_NEWER
            finisherPrompt.textWrappingMode = TextWrappingModes.NoWrap;   // "Ejecutar (falta Espíritu)" no entraba en un renglón
#else
            finisherPrompt.enableWordWrapping = false;
#endif
            UIFactory.Outline(finisherPrompt, 0.25f);
            interactPrompt = UIFactory.Text("Interact", world, "", 28, UIFactory.Paper, new Vector2(0, 0), Vector2.zero, new Vector2(420, 60), TextAlignmentOptions.Center);
            interactPrompt.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            UIFactory.Outline(interactPrompt, 0.25f);
        }

        EnemyWidget GetWidget(Enemy e)
        {
            if (widgetOf.TryGetValue(e, out var w)) return w;
            w = null;
            foreach (var x in widgets) if (x.enemy == null || !x.enemy.IsAlive || !x.enemy.gameObject.activeInHierarchy) { w = x; break; }
            if (w == null)
            {
                w = new EnemyWidget();
                w.rt = UIFactory.Rect("EnemyBar", world, Vector2.zero, Vector2.zero, new Vector2(0.5f, 0f), Vector2.zero, new Vector2(120, 30));
                w.hpBg = UIFactory.Image("Bg", w.rt, new Color(0.05f, 0.03f, 0.03f, 0.85f), new Vector2(0.5f, 0), new Vector2(0, 0), new Vector2(110, 9));
                w.hp = UIFactory.Image("Hp", w.hpBg.transform, new Color(0.85f, 0.15f, 0.1f), UIFactory.White);
                w.hp.type = Image.Type.Filled; w.hp.fillMethod = Image.FillMethod.Horizontal;
                w.hp.rectTransform.Fill(new Vector2(1, 1), new Vector2(-1, -1));
                w.pips = new Image[6];
                for (int i = 0; i < w.pips.Length; i++)
                {
                    var pip = UIFactory.Image("Pip" + i, w.rt, new Color(1, 1, 1, 0.2f), new Vector2(0.5f, 0), new Vector2((i - 2.5f) * 17f, 18f), new Vector2(11, 11));
                    pip.rectTransform.pivot = new Vector2(0.5f, 0.5f);
                    pip.rectTransform.localRotation = Quaternion.Euler(0, 0, 45);
                    w.pips[i] = pip;
                }
                w.status = UIFactory.Text("Status", w.rt, "", 26, UIFactory.Gold, new Vector2(0.5f, 0), new Vector2(0, 44), new Vector2(320, 40), TextAlignmentOptions.Center, true);
                // en un renglón: "¡DESEQUILIBRADO!" se partía en dos y crecía hasta pisar el aviso de ejecutar
#if UNITY_2023_2_OR_NEWER
                w.status.textWrappingMode = TextWrappingModes.NoWrap;
#else
                w.status.enableWordWrapping = false;
#endif
                UIFactory.Outline(w.status, 0.25f);
                widgets.Add(w);
            }
            if (w.enemy != null) widgetOf.Remove(w.enemy);
            w.enemy = e;
            widgetOf[e] = w;
            return w;
        }

        // la llama WorldMarkersLate, después de que la cámara fija su pose
        internal void UpdateWorldMarkers(float dt)
        {
            var cam = Game.Camera != null ? Game.Camera.Cam : null;
            var p = Game.Player;
            if (cam == null || p == null) { world.gameObject.SetActive(false); return; }
            world.gameObject.SetActive(!Game.InCutscene && !Game.IsPaused);
            float scale = root.localScale.x > 0 ? root.localScale.x : 1f;

            // barras de enemigos en combate
            var engaged = Game.Combat != null ? Game.Combat.Engaged : null;
            if (engaged != null)
                foreach (var e in engaged) { if (!(e is Boss)) GetWidget(e).visibleUntil = Time.time + 1.5f; }
            foreach (var w in widgets)
            {
                var e = w.enemy;
                bool show = e != null && e.IsAlive && e.gameObject.activeInHierarchy && (Time.time < w.visibleUntil || Time.time - e.LastHitTime < 3f) && !(e is Boss);
                Vector3 sp = show ? cam.WorldToScreenPoint(e.transform.position + Vector3.up * (e.config.height * e.config.scale + 0.35f)) : Vector3.zero;
                if (sp.z < 0f) show = false;
                w.rt.gameObject.SetActive(show);
                if (!show) continue;
                w.rt.anchoredPosition = new Vector2(sp.x, sp.y) / scale;
                w.hp.fillAmount = e.Health01;
                int max = Mathf.Min(e.config.maxImbalance, w.pips.Length);
                for (int i = 0; i < w.pips.Length; i++)
                {
                    w.pips[i].gameObject.SetActive(i < max);
                    if (i < max)
                    {
                        w.pips[i].rectTransform.anchoredPosition = new Vector2((i - (max - 1) * 0.5f) * 17f, 18f);
                        // las fracciones también se ven (parry perfecto +0.5, guardia imperfecta, rebote en la guardia):
                        // un pip a medias se enciende a medias. Antes pasaba de 1 pip a quebrado sin aviso
                        float f = Mathf.Clamp01(e.Imbalance - i);
                        Color off = new Color(1, 1, 1, 0.18f);
                        w.pips[i].color = f >= 0.99f ? (e.IsExhausted ? Color.Lerp(UIFactory.Gold, Color.white, 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 12f)) : UIFactory.Gold)
                            : f > 0.01f ? Color.Lerp(off, UIFactory.Gold, 0.25f + 0.45f * f) : off;
                    }
                }
                // agotado con la postura quebrada (se lo puede ejecutar) o solo abierto tras el combo (ventana de daño)
                w.status.text = e.PostureBroken ? "¡DESEQUILIBRADO!" : e.IsExhausted ? "¡ABIERTO!" : (e.State == EnemyState.Guard ? "<color=#9fc8ff>EN GUARDIA</color>" : "");
            }

            // fijado
            if (lockTarget != null && lockTarget.IsAlive)
            {
                Vector3 sp = cam.WorldToScreenPoint(lockTarget.AimPoint);
                lockReticle.gameObject.SetActive(sp.z > 0f);
                lockReticle.anchoredPosition = new Vector2(sp.x, sp.y) / scale;
                float pulse = 1f + 0.08f * Mathf.Sin(Time.unscaledTime * 8f);
                lockReticle.localScale = Vector3.one * pulse;
                lockReticle.localRotation = Quaternion.Euler(0, 0, 45 + Time.unscaledTime * 30f);
            }
            else lockReticle.gameObject.SetActive(false);

            // finisher
            var cand = p.FinisherCandidate();
            if (cand != null && p.State != PlayerState.Finisher)
            {
                // mismo punto que la barra del enemigo y corrido en unidades de canvas, encima del
                // "¡DESEQUILIBRADO!" (antes iba 1 m más arriba en el mundo: con la cámara alta eran ~40 px y se pisaban)
                Vector3 sp = cam.WorldToScreenPoint(cand.transform.position + Vector3.up * (cand.config.height * cand.config.scale + 0.35f));
                finisherPrompt.gameObject.SetActive(sp.z > 0f);
                bool afford = p.Spirit >= p.config.finisherCost;
                finisherPrompt.text = afford ? $"[{Game.Input?.Glyph(Act.Finisher)}] Ejecutar" : "<color=#888>Ejecutar (falta Espíritu)</color>";
                finisherPrompt.rectTransform.anchoredPosition = new Vector2(sp.x, sp.y) / scale + new Vector2(0f, 96f);
                finisherPrompt.transform.localScale = Vector3.one * (1f + 0.06f * Mathf.Sin(Time.unscaledTime * 9f));
            }
            else finisherPrompt.gameObject.SetActive(false);

            // interacción
            if (interactTarget != null && interactTarget.isActiveAndEnabled && p.State == PlayerState.Locomotion)
            {
                Vector3 sp = cam.WorldToScreenPoint(interactTarget.PromptPosition);
                interactPrompt.gameObject.SetActive(sp.z > 0f);
                interactPrompt.text = $"[{Game.Input?.Glyph(Act.Interact)}] {interactTarget.prompt}";
                interactPrompt.rectTransform.anchoredPosition = new Vector2(sp.x, sp.y) / scale;
            }
            else interactPrompt.gameObject.SetActive(false);

            // marcadores temporales (alerta "!", ataque imparable, guardia)
            for (int i = markers.Count - 1; i >= 0; i--)
            {
                var m = markers[i];
                m.t += dt;
                if (m.e == null || m.t > m.life || !m.e.gameObject.activeInHierarchy)
                {
                    // el contorno usa una instancia de material propia que TMP no destruye
                    var mat = m.text != null ? m.text.fontSharedMaterial : null;
                    if (mat != null && m.text.font != null && mat != m.text.font.material) Destroy(mat);
                    Destroy(m.rt.gameObject); markers.RemoveAt(i); continue;
                }
                Vector3 sp = cam.WorldToScreenPoint(m.e.transform.position + m.offset);
                m.rt.gameObject.SetActive(sp.z > 0f);
                m.rt.anchoredPosition = new Vector2(sp.x, sp.y) / scale;
                float k = m.t / m.life;
                float pop = k < 0.15f ? Mathf.Lerp(0.3f, 1.25f, k / 0.15f) : Mathf.Lerp(1.25f, 1f, Mathf.Clamp01((k - 0.15f) / 0.15f));
                m.rt.localScale = Vector3.one * pop;
                float fade = k > 0.75f ? 1f - (k - 0.75f) / 0.25f : 1f;
                if (m.text != null) { var c = m.text.color; c.a = fade; m.text.color = c; }
                if (m.icon != null) { var c = m.icon.color; c.a = fade; m.icon.color = c; m.rt.localRotation = Quaternion.Euler(0, 0, Mathf.Sin(m.t * 30f) * 6f * (1f - k)); }
            }
        }

        void AddMarker(Enemy e, string text, Color c, float size, float life)
        {
            if (e == null) return;
            var t = UIFactory.Text("Marker", world, text, size, c, new Vector2(0, 0), Vector2.zero, new Vector2(160, 120), TextAlignmentOptions.Center, true);
            t.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            UIFactory.Outline(t, 0.3f);
            markers.Add(new Marker { rt = t.rectTransform, text = t, e = e, life = life, offset = Vector3.up * (e.config.height * e.config.scale + 1.1f) });
        }

        /// <summary>Marcador con ícono dibujado (antes eran kanji que nadie entendía: 危 y 防).</summary>
        void AddIconMarker(Enemy e, Sprite icon, Color c, float size, float life)
        {
            if (e == null) return;
            if (icon == null) { AddMarker(e, "!", c, size, life); return; }
            var img = UIFactory.Image("Marker", world, c, Vector2.zero, Vector2.zero, new Vector2(size, size), icon);
            img.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            // sombra oscura detrás para que se lea sobre cualquier fondo
            var sh = UIFactory.Image("Shadow", img.transform, new Color(0, 0, 0, 0.55f), new Vector2(0.5f, 0.5f), new Vector2(3, -3), new Vector2(size * 1.06f, size * 1.06f), icon);
            sh.transform.SetAsFirstSibling();
            markers.Add(new Marker { rt = img.rectTransform, icon = img, e = e, life = life, offset = Vector3.up * (e.config.height * e.config.scale + 1.2f) });
        }

        public void ShowAlertMark(Enemy e) => AddMarker(e, "!", new Color(1f, 0.85f, 0.3f), 90, 1.1f);
        public void ShowDanger(Enemy e) => AddIconMarker(e, UISprites.Danger, new Color(1f, 0.18f, 0.1f), 92, 1.0f);
        public void ShowGuardMark(Enemy e) => AddIconMarker(e, UISprites.Guard, new Color(0.65f, 0.85f, 1f), 58, 0.7f);
        public void PulseImbalance(Enemy e) { if (e != null && !(e is Boss)) GetWidget(e).visibleUntil = Time.time + 3f; }
        public void SetLockTarget(Enemy e) => lockTarget = e;
        public void SetInteractPrompt(Interactable i) => interactTarget = i;
        public void HideInteractPrompt() => interactTarget = null;

        // ================================================================== overlay
        void BuildOverlay()
        {
            letterTop = UIFactory.Image("LetterTop", overlay, Color.black).rectTransform;
            letterTop.anchorMin = new Vector2(0, 1); letterTop.anchorMax = new Vector2(1, 1); letterTop.pivot = new Vector2(0.5f, 1); letterTop.sizeDelta = new Vector2(0, 0);
            letterBottom = UIFactory.Image("LetterBottom", overlay, Color.black).rectTransform;
            letterBottom.anchorMin = new Vector2(0, 0); letterBottom.anchorMax = new Vector2(1, 0); letterBottom.pivot = new Vector2(0.5f, 0); letterBottom.sizeDelta = new Vector2(0, 0);
            flashImage = UIFactory.Image("Flash", overlay, new Color(1, 1, 1, 0));
            flashImage.rectTransform.Fill(Vector2.zero, Vector2.zero);
            fadeImage = UIFactory.Image("Fade", overlay, new Color(0, 0, 0, 0));
            fadeImage.rectTransform.Fill(Vector2.zero, Vector2.zero);
            fadeImage.transform.SetAsLastSibling();
        }

        public void ScreenFlash(Color c, float duration)
        {
            flashColor = c; flashDur = Mathf.Max(0.01f, duration); flashT = 0f;
        }

        public void Letterbox(bool on) => letterboxTarget = on ? 1f : 0f;

        public void SetFade(float alpha) => fadeImage.color = new Color(0, 0, 0, alpha);

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
            flashT += dt;
            float k = Mathf.Clamp01(flashT / flashDur);
            var fc = flashColor; fc.a *= 1f - k; flashImage.color = fc;
            letterbox = Mathf.MoveTowards(letterbox, letterboxTarget, dt * 2.5f);
            float h = 120f * Mathf.SmoothStep(0f, 1f, letterbox);
            letterTop.sizeDelta = new Vector2(0, h);
            letterBottom.sizeDelta = new Vector2(0, h);
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
        public static void Fill(this RectTransform rt, Vector2 offsetMin, Vector2 offsetMax)
        {
            rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one; rt.pivot = new Vector2(0.5f, 0.5f);
            rt.offsetMin = offsetMin; rt.offsetMax = offsetMax;
        }
    }
}
