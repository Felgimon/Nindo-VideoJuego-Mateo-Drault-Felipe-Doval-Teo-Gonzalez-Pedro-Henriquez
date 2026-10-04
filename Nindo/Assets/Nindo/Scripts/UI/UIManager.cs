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

        // HUD
        Image healthFill, healthGhost, spiritFill, rageFill, rageGlow;
        RectTransform spiritRoot, healthRoot;
        TextMeshProUGUI objectiveText;
        Image[] sealIcons = new Image[3];
        float healthGhostValue = 1f, spiritShake;
        CanvasGroup hudGroup;

        // jefe
        CanvasGroup bossGroup;
        Image bossFill, bossGhost;
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

        class Marker { public RectTransform rt; public TextMeshProUGUI text; public Enemy e; public float t, life; public Vector3 offset; }
        readonly List<Marker> markers = new List<Marker>();

        Image fadeImage, flashImage;
        float flashT, flashDur;
        Color flashColor;
        RectTransform letterTop, letterBottom;
        float letterbox, letterboxTarget;

        void Awake()
        {
            Game.UI = this;
            UIFactory.EnsureEventSystem();
            canvas = UIFactory.CreateCanvas("Nindo UI", 10);
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

        // ================================================================== HUD
        void BuildHUD()
        {
            var c = Game.LoadContent();
            // --- vida (bandana) ---
            healthRoot = UIFactory.Rect("Health", hud, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), new Vector2(28, -22), new Vector2(560, 92));
            if (c.healthFrame != null)
            {
                var frame = UIFactory.Image("Frame", healthRoot, Color.white, c.healthFrame);
                Fill(frame.rectTransform);
                frame.preserveAspect = false;
            }
            else UIFactory.Image("Back", healthRoot, new Color(0.25f, 0.04f, 0.04f, 0.9f)).rectTransform.Fill(new Vector2(70, 22), new Vector2(-10, -22));
            healthGhost = MakeFill("Ghost", healthRoot, new Color(1f, 0.92f, 0.8f, 0.85f), c.healthFill, c.healthFillArea);
            healthFill = MakeFill("Fill", healthRoot, c.healthFill != null ? Color.white : UIFactory.Red, c.healthFill, c.healthFillArea);
            var hpLabel = UIFactory.Text("HP", healthRoot, "命", 30, UIFactory.Paper, new Vector2(0, 0.5f), new Vector2(-6, 0), new Vector2(60, 60), TextAlignmentOptions.Center, true);
            UIFactory.Outline(hpLabel);

            // --- espíritu (dragón) ---
            spiritRoot = UIFactory.Rect("Spirit", hud, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, -112), new Vector2(560, 84));
            if (c.spiritFrame != null)
            {
                var frame = UIFactory.Image("Frame", spiritRoot, Color.white, c.spiritFrame);
                Fill(frame.rectTransform);
            }
            else UIFactory.Image("Back", spiritRoot, new Color(0.25f, 0.18f, 0.04f, 0.9f)).rectTransform.Fill(new Vector2(70, 26), new Vector2(-10, -26));
            spiritFill = MakeFill("Fill", spiritRoot, c.spiritFill != null ? Color.white : UIFactory.Gold, c.spiritFill, c.spiritFillArea);
            var spLabel = UIFactory.Text("SP", spiritRoot, "魂", 28, UIFactory.Gold, new Vector2(0, 0.5f), new Vector2(-6, 0), new Vector2(60, 60), TextAlignmentOptions.Center, true);
            UIFactory.Outline(spLabel);

            // --- furia ---
            var rageRoot = UIFactory.Rect("Rage", hud, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), new Vector2(98, -198), new Vector2(380, 14));
            UIFactory.Image("Back", rageRoot, new Color(0.08f, 0.04f, 0.03f, 0.85f)).rectTransform.Fill(Vector2.zero, Vector2.zero);
            rageGlow = UIFactory.Image("Glow", rageRoot, new Color(1f, 0.45f, 0.1f, 0f));
            rageGlow.rectTransform.Fill(new Vector2(-8, -8), new Vector2(8, 8));
            rageFill = UIFactory.Image("Fill", rageRoot, new Color(1f, 0.45f, 0.15f), UIFactory.White);
            rageFill.type = Image.Type.Filled; rageFill.fillMethod = Image.FillMethod.Horizontal; rageFill.fillAmount = 0f;
            rageFill.rectTransform.Fill(new Vector2(2, 2), new Vector2(-2, -2));
            var rl = UIFactory.Text("RageLabel", rageRoot, "怒", 22, new Color(1f, 0.6f, 0.3f), new Vector2(0, 0.5f), new Vector2(-34, 0), new Vector2(30, 30), TextAlignmentOptions.Center, true);
            UIFactory.Outline(rl);

            // --- sellos (llaves) ---
            var seals = UIFactory.Rect("Seals", hud, new Vector2(1, 1), new Vector2(1, 1), new Vector2(1, 1), new Vector2(-30, -26), new Vector2(260, 84));
            string[] kanji = { "山", "水", "竹" };
            for (int i = 0; i < 3; i++)
            {
                var bg = UIFactory.Image("Seal" + i, seals, new Color(0.08f, 0.08f, 0.1f, 0.8f), new Vector2(0, 0.5f), new Vector2(i * 86, 0), new Vector2(72, 72));
                var t = UIFactory.Text("K", bg.transform, kanji[i], 40, new Color(1, 1, 1, 0.25f), TextAlignmentOptions.Center, true);
                t.rectTransform.Fill(Vector2.zero, Vector2.zero);
                sealIcons[i] = bg;
            }
            objectiveText = UIFactory.Text("Objective", hud, "", 26, UIFactory.Paper, new Vector2(1, 1), new Vector2(-30, -118), new Vector2(620, 80), TextAlignmentOptions.TopRight);
            UIFactory.Outline(objectiveText, 0.18f);
        }

        Image MakeFill(string name, RectTransform parent, Color c, Sprite sprite, Rect area)
        {
            var img = UIFactory.Image(name, parent, c, sprite != null ? sprite : UIFactory.White);
            img.type = Image.Type.Filled;
            img.fillMethod = Image.FillMethod.Horizontal;
            img.fillOrigin = 0;
            img.fillAmount = 1f;
            if (sprite != null)
            {
                var rt = img.rectTransform;
                rt.anchorMin = new Vector2(area.x, area.y);
                rt.anchorMax = new Vector2(area.x + area.width, area.y + area.height);
                rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero;
            }
            else img.rectTransform.Fill(new Vector2(70, 24), new Vector2(-12, -24));
            return img;
        }

        static void Fill(RectTransform rt) { rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one; rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero; }

        public void SetObjective(string text)
        {
            objectiveText.text = string.IsNullOrEmpty(text) ? "" : "<size=20><color=#e8c870>OBJETIVO</color></size>\n" + text;
        }

        public void DenySpirit() => spiritShake = 0.35f;

        void UpdateHUD(float dt)
        {
            var p = Game.Player;
            if (p == null) { hudGroup.alpha = 0f; return; }
            hudGroup.alpha = Mathf.MoveTowards(hudGroup.alpha, Game.InCutscene ? 0f : 1f, dt * 3f);
            float hp = p.Health01;
            healthFill.fillAmount = Mathf.MoveTowards(healthFill.fillAmount, hp, dt * 2.5f);
            if (hp < healthGhostValue) healthGhostValue = Mathf.MoveTowards(healthGhostValue, hp, dt * 0.45f); else healthGhostValue = hp;
            healthGhost.fillAmount = healthGhostValue;
            spiritFill.fillAmount = Mathf.MoveTowards(spiritFill.fillAmount, p.Spirit01, dt * 2f);
            spiritShake = Mathf.MoveTowards(spiritShake, 0f, dt);
            spiritRoot.anchoredPosition = new Vector2(18 + Mathf.Sin(Time.unscaledTime * 70f) * 10f * spiritShake, -112);
            spiritFill.color = spiritShake > 0f ? Color.Lerp(Color.white, new Color(1f, 0.3f, 0.3f), spiritShake * 2f) : Color.white;
            rageFill.fillAmount = p.Rage01;
            float glow = p.RageActive ? 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 10f) : (p.Rage01 > 0.85f ? 0.3f : 0f);
            rageGlow.color = new Color(1f, 0.45f, 0.1f, glow * 0.7f);
            for (int i = 0; i < 3; i++)
            {
                bool has = Game.Save.HasSeal((SealId)i);
                sealIcons[i].color = has ? new Color(0.85f, 0.65f, 0.2f, 0.95f) : new Color(0.08f, 0.08f, 0.1f, 0.8f);
                var t = sealIcons[i].GetComponentInChildren<TextMeshProUGUI>();
                if (t != null) t.color = has ? new Color(0.15f, 0.08f, 0.02f, 1f) : new Color(1, 1, 1, 0.25f);
            }
        }

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
        }

        public void ShowBossBar(Boss b)
        {
            boss = b; bossGhostValue = 1f;
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

            finisherPrompt = UIFactory.Text("Finisher", world, "", 30, UIFactory.Gold, new Vector2(0, 0), Vector2.zero, new Vector2(320, 60), TextAlignmentOptions.Center, true);
            finisherPrompt.rectTransform.pivot = new Vector2(0.5f, 0.5f);
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
                w.status = UIFactory.Text("Status", w.rt, "", 26, UIFactory.Gold, new Vector2(0.5f, 0), new Vector2(0, 44), new Vector2(200, 40), TextAlignmentOptions.Center, true);
                UIFactory.Outline(w.status, 0.25f);
                widgets.Add(w);
            }
            if (w.enemy != null) widgetOf.Remove(w.enemy);
            w.enemy = e;
            widgetOf[e] = w;
            return w;
        }

        void UpdateWorldMarkers(float dt)
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
                        bool filled = e.Imbalance >= i + 1 - 0.01f;
                        w.pips[i].color = filled ? (e.IsExhausted ? Color.Lerp(UIFactory.Gold, Color.white, 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 12f)) : UIFactory.Gold) : new Color(1, 1, 1, 0.18f);
                    }
                }
                w.status.text = e.IsExhausted ? "¡DESEQUILIBRADO!" : (e.State == EnemyState.Guard ? "<color=#9fc8ff>防</color>" : "");
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
                Vector3 sp = cam.WorldToScreenPoint(cand.transform.position + Vector3.up * (cand.config.height * cand.config.scale + 1.0f));
                finisherPrompt.gameObject.SetActive(sp.z > 0f);
                bool afford = p.Spirit >= p.config.finisherCost;
                finisherPrompt.text = afford ? $"[{Game.Input?.Glyph(Act.Finisher)}] 処刑 Ejecutar" : "<color=#888>Ejecutar (falta Espíritu)</color>";
                finisherPrompt.rectTransform.anchoredPosition = new Vector2(sp.x, sp.y) / scale;
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

            // marcadores temporales (!, 危, 防)
            for (int i = markers.Count - 1; i >= 0; i--)
            {
                var m = markers[i];
                m.t += dt;
                if (m.e == null || m.t > m.life || !m.e.gameObject.activeInHierarchy) { Destroy(m.rt.gameObject); markers.RemoveAt(i); continue; }
                Vector3 sp = cam.WorldToScreenPoint(m.e.transform.position + m.offset);
                m.rt.gameObject.SetActive(sp.z > 0f);
                m.rt.anchoredPosition = new Vector2(sp.x, sp.y) / scale;
                float k = m.t / m.life;
                float pop = k < 0.15f ? Mathf.Lerp(0.3f, 1.25f, k / 0.15f) : Mathf.Lerp(1.25f, 1f, Mathf.Clamp01((k - 0.15f) / 0.15f));
                m.rt.localScale = Vector3.one * pop;
                var c = m.text.color; c.a = k > 0.75f ? 1f - (k - 0.75f) / 0.25f : 1f; m.text.color = c;
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

        public void ShowAlertMark(Enemy e) => AddMarker(e, "!", new Color(1f, 0.85f, 0.3f), 90, 1.1f);
        public void ShowDanger(Enemy e) => AddMarker(e, "危", new Color(1f, 0.15f, 0.1f), 86, 1.0f);
        public void ShowGuardMark(Enemy e) => AddMarker(e, "防", new Color(0.65f, 0.85f, 1f), 60, 0.7f);
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
            UpdateWorldMarkers(dt);
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
