using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// HUD con el arte del equipo, vivo: la vida es la bandana roja y el Espíritu es el dragón dorado.
    /// Sin kanji (nadie los entendía) y sin barra aparte de furia: el Filo de Ira se lee en el dragón
    /// (el calor entra rojo desde la cabeza a medida que se carga y le arden los ojos; activo, el dragón
    /// se prende fuego y suelta brasas). Los efectos van en los shaders Nindo/UI Spirit y Nindo/UI Bandana.
    /// </summary>
    public partial class UIManager
    {
        Image healthFrame, healthFill, spiritFrame, spiritFill, spiritEye;
        Image healthFallbackGhost;   // sin shader: barra de daño clásica
        Material healthFrameMat, healthFillMat, spiritFrameMat, spiritFillMat;
        RectTransform spiritRoot, healthRoot, emberRoot;
        TextMeshProUGUI objectiveText;
        readonly Image[] sealRings = new Image[3], sealIcons = new Image[3];
        readonly bool[] sealHad = new bool[3];
        readonly float[] sealPop = new float[3];
        CanvasGroup hudGroup;

        float healthShown = 1f, healthGhostValue = 1f, healthGhostHold, healthHit, lastHealth = -1f;
        float spiritShown, spiritGhostValue, spiritGhostHold, spiritPulse, lastSpirit = -1f, spiritShake, rageShown, emberAcc;
        static readonly Vector2 HealthPos = new Vector2(28, -22), SpiritPos = new Vector2(18, -112);
        // dónde está la cabeza del dragón en el marco (el ojo no viene dibujado: lo pone el HUD)
        static readonly Vector2 DragonEye = new Vector2(0.918f, 0.64f), DragonMouth = new Vector2(0.975f, 0.47f);

        class Ember { public RectTransform rt; public Image img; public Vector2 vel; public float t, life, size; public bool mouth; }
        readonly List<Ember> embers = new List<Ember>();

        void BuildHUD()
        {
            var c = Game.LoadContent();
            var bandana = Resources.Load<Shader>("Shaders/NindoUIBandana");
            var dragon = Resources.Load<Shader>("Shaders/NindoUISpirit");

            // ---------------------------------------------------------------- vida (bandana)
            healthRoot = UIFactory.Rect("Health", hud, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), HealthPos, new Vector2(560, 92));
            if (c.healthFrame != null)
            {
                healthFrame = UIFactory.Image("Frame", healthRoot, Color.white, c.healthFrame);
                FillRect(healthFrame.rectTransform);
                healthFrameMat = MakeMat(bandana, healthFrame, 0f);
            }
            else UIFactory.Image("Back", healthRoot, new Color(0.25f, 0.04f, 0.04f, 0.9f)).rectTransform.Fill(new Vector2(70, 22), new Vector2(-10, -22));
            if (bandana == null) healthFallbackGhost = MakeFill("Ghost", healthRoot, new Color(1f, 0.92f, 0.8f, 0.85f), c.healthFill, c.healthFillArea, true);
            healthFill = MakeFill("Fill", healthRoot, c.healthFill != null ? Color.white : UIFactory.Red, c.healthFill, c.healthFillArea, bandana == null);
            healthFillMat = MakeMat(bandana, healthFill, 1f);

            // ---------------------------------------------------------------- espíritu (dragón)
            spiritRoot = UIFactory.Rect("Spirit", hud, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), SpiritPos, new Vector2(560, 84));
            if (c.spiritFrame != null)
            {
                spiritFrame = UIFactory.Image("Frame", spiritRoot, Color.white, c.spiritFrame);
                FillRect(spiritFrame.rectTransform);
                spiritFrameMat = MakeMat(dragon, spiritFrame, 0f);
            }
            else UIFactory.Image("Back", spiritRoot, new Color(0.25f, 0.18f, 0.04f, 0.9f)).rectTransform.Fill(new Vector2(70, 26), new Vector2(-10, -26));
            spiritFill = MakeFill("Fill", spiritRoot, c.spiritFill != null ? Color.white : UIFactory.Gold, c.spiritFill, c.spiritFillArea, dragon == null);
            spiritFillMat = MakeMat(dragon, spiritFill, 1f);
            spiritEye = UIFactory.Image("Eye", spiritRoot, new Color(1f, 0.6f, 0.2f, 0f), DragonEye, Vector2.zero, new Vector2(30, 30), UISprites.SoftDot);
            spiritEye.rectTransform.anchorMin = spiritEye.rectTransform.anchorMax = DragonEye;
            emberRoot = UIFactory.Rect("Embers", spiritRoot, Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);

            // ---------------------------------------------------------------- sellos (montaña, lago, bambú)
            var seals = UIFactory.Rect("Seals", hud, new Vector2(1, 1), new Vector2(1, 1), new Vector2(1, 1), new Vector2(-30, -26), new Vector2(260, 84));
            Sprite[] icons = { UISprites.SealMountain, UISprites.SealWater, UISprites.SealBamboo };
            for (int i = 0; i < 3; i++)
            {
                sealRings[i] = UIFactory.Image("Seal" + i, seals, new Color(0.08f, 0.08f, 0.1f, 0.8f), new Vector2(0, 0.5f), new Vector2(i * 86 + 38, 0), new Vector2(76, 76), UISprites.SealRing);
                sealRings[i].rectTransform.pivot = new Vector2(0.5f, 0.5f);
                sealIcons[i] = UIFactory.Image("Icon", sealRings[i].transform, new Color(1, 1, 1, 0.2f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(50, 50), icons[i]);
                sealIcons[i].rectTransform.pivot = new Vector2(0.5f, 0.5f);
            }
            objectiveText = UIFactory.Text("Objective", hud, "", 26, UIFactory.Paper, new Vector2(1, 1), new Vector2(-30, -118), new Vector2(620, 80), TextAlignmentOptions.TopRight);
            UIFactory.Outline(objectiveText, 0.18f);
        }

        static Material MakeMat(Shader sh, Image img, float mode)
        {
            if (sh == null || img == null) return null;
            var m = new Material(sh) { name = img.name + "_" + sh.name };
            m.SetFloat("_Mode", mode);
            img.material = m;
            return m;
        }

        /// <summary>Relleno ubicado en el área de la barra. Con shader el recorte lo hace el shader (borde
        /// vivo, estela); sin shader, Image.Filled clásico.</summary>
        Image MakeFill(string name, RectTransform parent, Color c, Sprite sprite, Rect area, bool filled)
        {
            var img = UIFactory.Image(name, parent, c, sprite != null ? sprite : UIFactory.White);
            if (filled)
            {
                img.type = Image.Type.Filled;
                img.fillMethod = Image.FillMethod.Horizontal;
                img.fillOrigin = 0;
                img.fillAmount = 1f;
            }
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

        static void FillRect(RectTransform rt) { rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one; rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero; }

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
            float t = Time.unscaledTime;

            // ---------------------------------------------------------------- vida
            float hp = p.Health01;
            if (lastHealth < 0f) { lastHealth = hp; healthShown = hp; healthGhostValue = hp; }
            if (hp < lastHealth - 0.001f) { healthHit = 1f; healthGhostValue = Mathf.Max(healthGhostValue, healthShown); healthGhostHold = 0.45f; }
            lastHealth = hp;
            healthShown = Mathf.MoveTowards(healthShown, hp, dt * (hp < healthShown ? 4f : 1.2f));
            healthGhostHold -= dt;
            if (healthGhostHold <= 0f) healthGhostValue = Mathf.MoveTowards(healthGhostValue, healthShown, dt * 0.5f);
            if (healthGhostValue < healthShown) healthGhostValue = healthShown;
            healthHit = Mathf.MoveTowards(healthHit, 0f, dt * 3.5f);
            // latido con poca vida (lub-dub, ~70 por minuto)
            float low = hp > 0f && hp < 0.3f ? 0.45f + 0.55f * (0.3f - hp) / 0.3f : 0f;
            float ph = Mathf.Repeat(t / 0.86f, 1f);
            float beat = Mathf.Exp(-Mathf.Pow(ph / 0.05f, 2)) + 0.6f * Mathf.Exp(-Mathf.Pow((ph - 0.18f) / 0.05f, 2));
            float lowPulse = low * beat;
            healthRoot.localScale = Vector3.one * (1f + lowPulse * 0.035f + healthHit * 0.03f);
            healthRoot.anchoredPosition = HealthPos + new Vector2(Mathf.Sin(t * 83f), Mathf.Cos(t * 67f)) * 5f * healthHit * healthHit;
            if (healthFillMat != null)
            {
                SetBandana(healthFrameMat, healthShown, healthGhostValue, healthHit, lowPulse, t);
                SetBandana(healthFillMat, healthShown, healthGhostValue, healthHit, lowPulse, t);
            }
            else
            {
                healthFill.fillAmount = healthShown;
                if (healthFallbackGhost != null) healthFallbackGhost.fillAmount = healthGhostValue;
            }

            // ---------------------------------------------------------------- espíritu + Filo de Ira
            float sp = p.Spirit01;
            if (lastSpirit < 0f) { lastSpirit = sp; spiritShown = sp; spiritGhostValue = sp; }
            if (sp < lastSpirit - 0.001f) { spiritGhostValue = Mathf.Max(spiritGhostValue, spiritShown); spiritGhostHold = 0.3f; }
            else if (sp > lastSpirit + 0.001f) spiritPulse = Mathf.Max(spiritPulse, Mathf.Clamp01(0.35f + (sp - lastSpirit) * 5f));
            lastSpirit = sp;
            spiritShown = Mathf.MoveTowards(spiritShown, sp, dt * (sp < spiritShown ? 5f : 1.4f));
            spiritGhostHold -= dt;
            if (spiritGhostHold <= 0f) spiritGhostValue = Mathf.MoveTowards(spiritGhostValue, spiritShown, dt * 0.55f);
            if (spiritGhostValue < spiritShown) spiritGhostValue = spiritShown;
            spiritPulse = Mathf.MoveTowards(spiritPulse, 0f, dt * 2.2f);
            spiritShake = Mathf.MoveTowards(spiritShake, 0f, dt);
            rageShown = Mathf.MoveTowards(rageShown, p.RageActive ? 1f : 0f, dt * 2.5f);
            float heat = p.RageActive ? 1f : p.Rage01;
            spiritRoot.anchoredPosition = SpiritPos + new Vector2(Mathf.Sin(t * 70f) * 10f * spiritShake, 0f);
            spiritRoot.localScale = Vector3.one * (1f + 0.045f * spiritPulse * spiritPulse);
            if (spiritFillMat != null)
            {
                SetDragon(spiritFrameMat, spiritShown, spiritGhostValue, heat, rageShown, t);
                SetDragon(spiritFillMat, spiritShown, spiritGhostValue, heat, rageShown, t);
            }
            else
            {
                spiritFill.fillAmount = spiritShown;
                spiritFill.color = spiritShake > 0f ? Color.Lerp(Color.white, new Color(1f, 0.3f, 0.3f), spiritShake * 2f) : Color.white;
            }

            // ojo: se enciende con el calor; en ira arde y titila
            float flick = 0.75f + 0.25f * Mathf.PerlinNoise(t * 9f, 0.3f);
            float eyeA = Mathf.Max(Mathf.InverseLerp(0.15f, 1f, heat) * 0.85f, rageShown * flick);
            spiritEye.color = new Color(1f, Mathf.Lerp(0.85f, 0.4f, heat), Mathf.Lerp(0.4f, 0.12f, heat), eyeA);
            spiritEye.rectTransform.sizeDelta = Vector2.one * (22f + 18f * heat + 10f * rageShown * flick);
            UpdateEmbers(dt, heat);

            // ---------------------------------------------------------------- sellos
            for (int i = 0; i < 3; i++)
            {
                bool has = Game.Save.HasSeal((SealId)i);
                if (has && !sealHad[i] && Time.timeSinceLevelLoad > 2f) sealPop[i] = 1f;   // recién obtenido (no al cargar)
                sealHad[i] = has;
                sealPop[i] = Mathf.MoveTowards(sealPop[i], 0f, dt * 0.8f);
                float pop = sealPop[i];
                sealRings[i].color = has ? Color.Lerp(new Color(0.85f, 0.65f, 0.2f, 0.95f), new Color(1f, 0.95f, 0.7f, 1f), pop) : new Color(0.08f, 0.08f, 0.1f, 0.75f);
                sealIcons[i].color = has ? new Color(0.17f, 0.08f, 0.02f, 1f) : new Color(1, 1, 1, 0.2f);
                sealRings[i].rectTransform.localScale = Vector3.one * (1f + 0.45f * Mathf.Sin(pop * Mathf.PI) * pop);
                sealRings[i].rectTransform.localRotation = Quaternion.Euler(0, 0, pop * pop * 360f);
            }
        }

        static void SetBandana(Material m, float fill, float ghost, float hit, float low, float t)
        {
            if (m == null) return;
            m.SetFloat("_Fill", fill); m.SetFloat("_Ghost", ghost); m.SetFloat("_Hit", hit); m.SetFloat("_Low", low); m.SetFloat("_T", t);
        }

        void SetDragon(Material m, float fill, float ghost, float heat, float rage, float t)
        {
            if (m == null) return;
            m.SetFloat("_Fill", fill); m.SetFloat("_Ghost", ghost); m.SetFloat("_Heat", heat); m.SetFloat("_Rage", rage);
            m.SetFloat("_Pulse", spiritPulse); m.SetFloat("_Deny", Mathf.Clamp01(spiritShake * 2.8f)); m.SetFloat("_T", t);
        }

        // ---------------------------------------------------------------- brasas del dragón
        /// <summary>Línea media aproximada del cuerpo del dragón en el marco (x, y normalizados, y desde abajo).</summary>
        static float DragonBodyY(float x) => 0.5f + 0.12f * Mathf.Sin((x - 0.22f) * Mathf.PI * 2f * 0.95f);

        void UpdateEmbers(float dt, float heat)
        {
            if (emberRoot == null || UISprites.SoftDot == null) return;
            float rate = rageShown * 26f + (rageShown < 0.5f ? Mathf.Max(0f, heat - 0.6f) * 28f : 0f);
            emberAcc += rate * dt;
            var size = emberRoot.rect.size;
            while (emberAcc >= 1f)
            {
                emberAcc -= 1f;
                bool mouth = rageShown > 0.5f && Random.value < 0.3f;
                Vector2 n = mouth ? DragonMouth : new Vector2(Random.Range(0.08f, 0.95f), 0f);
                if (!mouth) n.y = DragonBodyY(n.x) + Random.Range(-0.08f, 0.12f);
                SpawnEmber(new Vector2((n.x - 0.5f) * size.x, (n.y - 0.5f) * size.y), mouth);
            }
            for (int i = 0; i < embers.Count; i++)
            {
                var e = embers[i];
                if (!e.rt.gameObject.activeSelf) continue;
                e.t += dt;
                float k = e.t / e.life;
                if (k >= 1f) { e.rt.gameObject.SetActive(false); continue; }
                e.vel += new Vector2(Mathf.Sin(e.t * 7f + i) * 40f, 30f) * dt;
                e.rt.anchoredPosition += e.vel * dt;
                e.rt.sizeDelta = Vector2.one * e.size * (1f - k * 0.7f);
                // amarillo -> naranja -> rojo, y se apaga
                var col = k < 0.4f ? Color.Lerp(new Color(1f, 0.9f, 0.5f), new Color(1f, 0.5f, 0.12f), k / 0.4f) : Color.Lerp(new Color(1f, 0.5f, 0.12f), new Color(0.8f, 0.12f, 0.05f), (k - 0.4f) / 0.6f);
                col.a = (k < 0.15f ? k / 0.15f : 1f - (k - 0.15f) / 0.85f) * 0.95f;
                e.img.color = col;
            }
        }

        void SpawnEmber(Vector2 pos, bool mouth)
        {
            Ember e = null;
            foreach (var x in embers) if (!x.rt.gameObject.activeSelf) { e = x; break; }
            if (e == null)
            {
                if (embers.Count >= 60) return;
                var img = UIFactory.Image("Ember", emberRoot, Color.clear, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(10, 10), UISprites.SoftDot);
                img.rectTransform.pivot = new Vector2(0.5f, 0.5f);
                e = new Ember { rt = img.rectTransform, img = img };
                embers.Add(e);
            }
            e.rt.gameObject.SetActive(true);
            e.rt.anchoredPosition = pos;
            e.t = 0f;
            e.mouth = mouth;
            e.life = mouth ? Random.Range(0.35f, 0.6f) : Random.Range(0.55f, 1.05f);
            e.size = mouth ? Random.Range(12f, 22f) : Random.Range(6f, 14f);
            e.vel = mouth ? new Vector2(Random.Range(70f, 150f), Random.Range(5f, 45f)) : new Vector2(Random.Range(-15f, 15f), Random.Range(45f, 100f));
        }
    }

    /// <summary>Sprites de UI dibujados por Tools/UI/build_ui_art.py (Resources/UI). Pueden faltar: quien
    /// los usa tiene que tolerar null.</summary>
    public static class UISprites
    {
        static Sprite Load(ref Sprite cache, string name) => cache != null ? cache : (cache = Resources.Load<Sprite>("UI/" + name));
        static Sprite danger, guard, ring, mountain, water, bamboo, dot;
        public static Sprite Danger => Load(ref danger, "IconDanger");
        public static Sprite Guard => Load(ref guard, "IconGuard");
        public static Sprite SealRing => Load(ref ring, "SealRing");
        public static Sprite SealMountain => Load(ref mountain, "SealMountain");
        public static Sprite SealWater => Load(ref water, "SealWater");
        public static Sprite SealBamboo => Load(ref bamboo, "SealBamboo");
        public static Sprite SoftDot => Load(ref dot, "SoftDot");
    }
}
