using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// El HUD es SOLO el arte del equipo: la bandana roja (vida) y el dragón dorado (Espíritu). Nada de barras
    /// extra: el Filo de Ira vive en el lomo del dragón (brasa que avanza de la cola a la cabeza al cargarse,
    /// lenguas de fuego cuando está listo, el dragón arde mientras dura y las llamas se retiran hacia la cola
    /// con el tiempo que queda). El dragón está vivo: nada, respira, cabecea, parpadea, le brillan las escamas,
    /// se apaga sin Espíritu para el dash, ruge al encenderse y raya en rojo lo que falta para pagar algo.
    /// Arriba a la derecha, los tres sellos (pictogramas con contorno de tinta) y el objetivo, que se aparta
    /// en combate. Shaders: Nindo/UI Spirit y Nindo/UI Bandana.
    /// </summary>
    public partial class UIManager
    {
        // grupos: izquierda (bandana + dragón, se mueve cada cuadro: canvas propio) y derecha (sellos + objetivo)
        CanvasGroup hudGroup, leftGroup, rightGroup, objectiveGroup;
        RectTransform hudLeft, hudRight;

        // ---- bandana
        RectTransform healthRoot;
        Image healthFrame, healthFill, healthFallbackGhost;
        Material healthFrameMat, healthFillMat;
        float healthShown = 1f, healthGhostValue = 1f, healthGhostHold, healthHit, healthFlash, lastHealth = -1f, healX = 2f, healA;

        // ---- dragón
        RectTransform spiritRoot, spiritBody, eyeRt, emberRoot;
        Image spiritFrame, spiritFill, eyeImg, eyeGlow, glintImg;
        Material spiritFrameMat, spiritFillMat;
        Vector2 spiritSize;
        float spiritShown, spiritGhostValue, spiritGhostHold, spiritGhostAge = 1f, spiritPulse, lastSpirit = -1f, spiritShake;
        float rageShown, readyShown, dimShown, rageFrontShown, lastRage01, needValue, needA, needHold, sparkA, sparkX, roar = 1f;
        float emberAcc, mouthAcc, blinkT = 1f, nextBlink = 3f, lidShown = 1f;
        bool wasRageActive;
        readonly float[] crest = new float[64], skin = new float[64];

        // ---- sellos y objetivo
        readonly Image[] sealDiscs = new Image[3], sealIcons = new Image[3], sealRings = new Image[3];
        readonly bool[] sealHad = new bool[3];
        readonly float[] sealPop = new float[3], sealRingT = { 9f, 9f, 9f };
        Image sealLink;
        float sealLinkT = -1f, sealVisibleUntil;
        int sealLinkPulsed;
        TextMeshProUGUI objectiveText;
        Image objectiveLine;
        string objective = "";
        Coroutine objectiveRoutine;

        // bandana: el arte se ve a 92 px por cada 339 del sprite original (alto de la banda en pantalla) y el sprite
        // ahora tiene 30 px de aire arriba y abajo: la banda queda donde estaba (arriba a 22 px del borde)
        const float HealthScale = 92f / 339f;
        static readonly Vector2 HealthPos = new Vector2(28f, -22f - 6f * HealthScale + 30f * HealthScale);
        // dragón: proporción nativa (antes se aplastaba 1.11x) y la cresta a la altura de siempre
        static readonly Vector2 SpiritPos = new Vector2(18f, -90f);
        // dónde están el ojo y la boca en el marco (u a lo largo, v desde abajo): el arte no trae ojo, lo pone el HUD
        static readonly Vector2 DragonEye = new Vector2(0.9256f, 0.5122f), DragonMouth = new Vector2(0.975f, 0.427f);
        // la ola del dragón: los mismos números que se le pasan al shader (DragonWave los repite en C#)
        const float WaveAmp = 0.03f, WaveFreq = 0.012f, WaveSpeed = 1.8f;

        class Ember { public RectTransform rt; public Image img; public Vector2 vel; public float t, life, size; public Color c0, c1, c2; }
        readonly List<Ember> embers = new List<Ember>();

        static readonly int IdFill = Shader.PropertyToID("_Fill"), IdGhost = Shader.PropertyToID("_Ghost"), IdGhostAge = Shader.PropertyToID("_GhostAge"),
            IdNeed = Shader.PropertyToID("_Need"), IdNeedA = Shader.PropertyToID("_NeedA"), IdNod = Shader.PropertyToID("_Nod"),
            IdRageFront = Shader.PropertyToID("_RageFront"), IdReady = Shader.PropertyToID("_Ready"), IdRageOn = Shader.PropertyToID("_RageOn"),
            IdPulse = Shader.PropertyToID("_Pulse"), IdDeny = Shader.PropertyToID("_Deny"), IdDim = Shader.PropertyToID("_Dim"),
            IdSpark = Shader.PropertyToID("_Spark"), IdSparkX = Shader.PropertyToID("_SparkX"), IdT = Shader.PropertyToID("_T"),
            IdHit = Shader.PropertyToID("_Hit"), IdFlash = Shader.PropertyToID("_Flash"), IdHeal = Shader.PropertyToID("_Heal"),
            IdHealA = Shader.PropertyToID("_HealA"), IdLow = Shader.PropertyToID("_Low");

        void BuildHUD()
        {
            var c = Game.LoadContent();
            var bandana = Resources.Load<Shader>("Shaders/NindoUIBandana");
            var dragon = Resources.Load<Shader>("Shaders/NindoUISpirit");

            hudLeft = UIFactory.Stretch("Left", hud);
            leftGroup = hudLeft.gameObject.AddComponent<CanvasGroup>();
            UIFactory.Nest(hudLeft);
            hudRight = UIFactory.Stretch("Right", hud);
            rightGroup = hudRight.gameObject.AddComponent<CanvasGroup>();
            UIFactory.Nest(hudRight);
            // sombra de tinta difusa detrás de cada esquina: sobre la nieve el HUD se perdía
            UIFactory.Centered("Scrim", hudLeft, new Color(0.04f, 0.035f, 0.05f, 0.42f), new Vector2(0f, 1f), new Vector2(250f, -80f), new Vector2(1150, 520), UISprites.SoftDot);
            UIFactory.Centered("Scrim", hudRight, new Color(0.04f, 0.035f, 0.05f, 0.36f), new Vector2(1f, 1f), new Vector2(-230f, -70f), new Vector2(1000, 440), UISprites.SoftDot);

            // ---------------------------------------------------------------- vida (bandana)
            Sprite hf = c.healthFrame;
            float hh = hf != null ? hf.rect.height * HealthScale : 92f;
            healthRoot = UIFactory.Rect("Health", hudLeft, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), HealthPos, new Vector2(560, hh));
            if (hf != null)
            {
                // 9-slice: el nudo y las puntas mantienen su forma a cualquier ancho (antes se estiraban 1.4x)
                healthFrame = UIFactory.Sliced("Frame", healthRoot, hf, Color.white, hh);
                FillRect(healthFrame.rectTransform);
                healthFrameMat = MakeMat(bandana, healthFrame, 0f);
            }
            else UIFactory.Image("Back", healthRoot, new Color(0.25f, 0.04f, 0.04f, 0.9f)).rectTransform.Fill(new Vector2(70, 22), new Vector2(-10, -22));
            if (bandana == null) healthFallbackGhost = MakeFill("Ghost", healthRoot, new Color(1f, 0.92f, 0.8f, 0.85f), c.healthFill, true);
            healthFill = MakeFill("Fill", healthRoot, c.healthFill != null ? Color.white : UIFactory.Red, c.healthFill, bandana == null);
            if (c.healthFill != null && hf != null) PlaceOnSliced(healthFill.rectTransform, hf, c.healthFillArea, 560f, hh);
            if (healthFallbackGhost != null && hf != null) PlaceOnSliced(healthFallbackGhost.rectTransform, hf, c.healthFillArea, 560f, hh);
            healthFillMat = MakeMat(bandana, healthFill, 1f);

            // ---------------------------------------------------------------- espíritu (dragón)
            Sprite sf = c.spiritFrame;
            spiritSize = new Vector2(560f, sf != null ? 560f * sf.rect.height / sf.rect.width : 84f);
            spiritRoot = UIFactory.Rect("Spirit", hudLeft, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), SpiritPos, spiritSize);
            spiritBody = UIFactory.Stretch("Body", spiritRoot);
            spiritBody.pivot = new Vector2(0.3f, 0.5f);   // respira y ruge desde el cuerpo, no desde el centro del quad
            if (sf != null)
            {
                spiritFrame = UIFactory.Image("Frame", spiritBody, Color.white, sf);
                FillRect(spiritFrame.rectTransform);
                spiritFrameMat = MakeMat(dragon, spiritFrame, 0f);
                SetDragonGeometry(spiritFrameMat, 1f, 0f);
            }
            else UIFactory.Image("Back", spiritBody, new Color(0.25f, 0.18f, 0.04f, 0.9f)).rectTransform.Fill(new Vector2(70, 26), new Vector2(-10, -26));
            spiritFill = MakeFill("Fill", spiritBody, c.spiritFill != null ? Color.white : UIFactory.Gold, c.spiritFill, dragon == null);
            if (c.spiritFill != null)
            {
                var a = c.spiritFillArea;
                var rt = spiritFill.rectTransform;
                rt.anchorMin = new Vector2(a.x, 0f); rt.anchorMax = new Vector2(a.x + a.width, 1f);
                rt.offsetMin = rt.offsetMax = Vector2.zero;
            }
            spiritFillMat = MakeMat(dragon, spiritFill, 1f);
            if (spiritFillMat != null) SetDragonGeometry(spiritFillMat, c.spiritFillArea.width, c.spiritFillArea.x);

            // ojo: brillo de fuego detrás (ira), almendra con pupila rasgada y un destello que nunca se apaga
            eyeGlow = UIFactory.Centered("EyeGlow", spiritBody, new Color(1f, 0.45f, 0.1f, 0f), DragonEye, Vector2.zero, new Vector2(22, 22), UISprites.SoftDot);
            eyeImg = UIFactory.Centered("Eye", spiritBody, EyeGold, DragonEye, Vector2.zero, new Vector2(15f, 9.5f), UISprites.DragonEye);
            eyeRt = eyeImg.rectTransform;
            glintImg = UIFactory.Centered("Glint", eyeRt, new Color(1f, 1f, 0.92f, 0.95f), new Vector2(0.42f, 0.66f), Vector2.zero, new Vector2(4.5f, 4.5f), UISprites.SoftDot);
            emberRoot = UIFactory.Rect("Embers", spiritBody, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            ReadDragonProfile();

            // ---------------------------------------------------------------- sellos (montaña, lago, bambú)
            var seals = UIFactory.Rect("Seals", hudRight, new Vector2(1, 1), new Vector2(1, 1), new Vector2(1, 1), new Vector2(-30, -26), new Vector2(264, 84));
            sealLink = UIFactory.Image("Link", seals, UIFactory.Gold, new Vector2(0f, 0.5f), new Vector2(38f, 0f), new Vector2(176f, 14f), UISprites.BrushLine);
            sealLink.rectTransform.pivot = new Vector2(0f, 0.5f);
            sealLink.type = Image.Type.Filled; sealLink.fillMethod = Image.FillMethod.Horizontal; sealLink.fillAmount = 0f;
            for (int i = 0; i < 3; i++)
            {
                var pos = new Vector2(i * 88 + 38, 0);
                sealRings[i] = UIFactory.Centered("Burst" + i, seals, new Color(1f, 0.85f, 0.4f, 0f), new Vector2(0, 0.5f), pos, new Vector2(80, 80), UISprites.Ring);
                sealDiscs[i] = UIFactory.Centered("Seal" + i, seals, UIFactory.Lacquer, new Vector2(0, 0.5f), pos, new Vector2(76, 76), UISprites.SealDisc);
                sealIcons[i] = UIFactory.Centered("Icon", sealDiscs[i].transform, SealIconEmpty, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(46, 46), UISprites.Get(UISprites.SealIconName((SealId)i)));
                sealHad[i] = Game.Save.HasSeal((SealId)i);
            }
            if (Game.Save.SealCount >= 3) sealLink.fillAmount = 1f;

            // ---------------------------------------------------------------- objetivo
            var obj = UIFactory.Rect("Objective", hudRight, new Vector2(1, 1), new Vector2(1, 1), new Vector2(1, 1), new Vector2(-8, -116), new Vector2(720, 112));
            objectiveGroup = obj.gameObject.AddComponent<CanvasGroup>();
            objectiveGroup.alpha = 0f;
            var sw = UIFactory.Image("Swash", obj, new Color(0.043f, 0.039f, 0.051f, 0.62f), UISprites.BrushSwash);
            FillRect(sw.rectTransform);
            sw.rectTransform.localScale = new Vector3(-1f, 1f, 1f);   // la tinta se junta a la derecha, contra el borde
            var lbl = UIFactory.Text("Label", obj, "OBJETIVO", 20, UIFactory.Gold, new Vector2(1, 1), new Vector2(-26, -12), new Vector2(300, 26), TextAlignmentOptions.TopRight);
            UIFactory.Outline(lbl, 0.15f);
            float lw = lbl.GetPreferredValues("OBJETIVO", 300f, 26f).x;
            UIFactory.Centered("Bullet", obj, UIFactory.Gold, new Vector2(1, 1), new Vector2(-26f - lw - 36f, -24f), new Vector2(50, 18), UISprites.Kunai);
            objectiveText = UIFactory.Text("Text", obj, "", 27, UIFactory.Paper, new Vector2(1, 1), new Vector2(-26, -38), new Vector2(640, 66), TextAlignmentOptions.TopRight);
            objectiveText.enableAutoSizing = true; objectiveText.fontSizeMin = 21; objectiveText.fontSizeMax = 27;
            UIFactory.Outline(objectiveText, 0.18f);
            objectiveLine = UIFactory.Image("Line", obj, UIFactory.Gold, new Vector2(1, 0), new Vector2(-24, 6), new Vector2(380, 10), UISprites.BrushLine);
            objectiveLine.type = Image.Type.Filled; objectiveLine.fillMethod = Image.FillMethod.Horizontal; objectiveLine.fillOrigin = 1; objectiveLine.fillAmount = 0f;
        }

        static readonly Color EyeGold = new Color(1f, 0.8f, 0.28f, 1f);
        static readonly Color SealIconEmpty = new Color(0.59f, 0.57f, 0.63f, 0.6f), SealIconHas = new Color(0.16f, 0.086f, 0.03f, 1f), SealGold = new Color(0.88f, 0.67f, 0.2f, 1f);

        static Material MakeMat(Shader sh, Image img, float mode)
        {
            if (sh == null || img == null) return null;
            var m = new Material(sh) { name = img.name + "_" + sh.name };
            m.SetFloat("_Mode", mode);
            img.material = m;
            return m;
        }

        /// <summary>u = uv.x * escala + offset (0 cola, 1 hocico) y medidas en canvas, para que la ola del marco,
        /// la del relleno y la que calcula C# para el ojo sean la misma.</summary>
        void SetDragonGeometry(Material m, float uScale, float uOffset)
        {
            m.SetFloat("_UScale", uScale); m.SetFloat("_UOffset", uOffset);
            m.SetFloat("_Len", spiritSize.x); m.SetFloat("_Height", spiritSize.y);
            m.SetFloat("_WaveAmp", WaveAmp); m.SetFloat("_WaveFreq", WaveFreq); m.SetFloat("_WaveSpeed", WaveSpeed);
            var prof = UISprites.SpiritProfile;
            if (prof != null) m.SetTexture("_Dorsal", prof);
        }

        /// <summary>Relleno: con shader el recorte lo hace el shader (borde vivo, estela); sin shader, Image.Filled clásico.</summary>
        Image MakeFill(string name, RectTransform parent, Color c, Sprite sprite, bool filled)
        {
            var img = UIFactory.Image(name, parent, c, sprite != null ? sprite : UIFactory.White);
            if (filled)
            {
                img.type = Image.Type.Filled;
                img.fillMethod = Image.FillMethod.Horizontal;
                img.fillOrigin = 0;
                img.fillAmount = 1f;
            }
            if (sprite == null) img.rectTransform.Fill(new Vector2(70, 24), new Vector2(-12, -24));
            return img;
        }

        /// <summary>
        /// Ubica el relleno sobre un marco 9-slice: los extremos del área (en píxeles del sprite) se pasan por el
        /// mismo mapeo que el marco (puntas a escala, medio estirado), así el relleno calza en la banda.
        /// </summary>
        static void PlaceOnSliced(RectTransform fill, Sprite frame, Rect area, float width, float height)
        {
            float w = frame.rect.width, k = height / frame.rect.height;
            float L = frame.border.x, R = frame.border.z;
            float Map(float x) => x <= L ? x * k : x >= w - R ? width - (w - x) * k : L * k + (x - L) / Mathf.Max(1f, w - L - R) * (width - (L + R) * k);
            float x0 = Map(area.x * w), x1 = Map((area.x + area.width) * w);
            fill.anchorMin = new Vector2(0f, 0f); fill.anchorMax = new Vector2(0f, 1f); fill.pivot = new Vector2(0f, 0.5f);
            fill.anchoredPosition = new Vector2(x0, 0f); fill.sizeDelta = new Vector2(x1 - x0, 0f);
        }

        static void FillRect(RectTransform rt) { rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one; rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero; }

        /// <summary>Perfil del lomo (Resources/UI/SpiritProfile, medido del sprite) para las brasas: sale de la cresta.</summary>
        void ReadDragonProfile()
        {
            var tex = UISprites.SpiritProfile;
            Color32[] px = null;
            if (tex != null && tex.isReadable) px = tex.GetPixels32();
            for (int i = 0; i < crest.Length; i++)
            {
                if (px == null) { crest[i] = 0.62f; skin[i] = 0.58f; continue; }
                int x = Mathf.Clamp(Mathf.RoundToInt(i / (crest.Length - 1f) * (tex.width - 1)), 0, tex.width - 1);
                crest[i] = px[x].r / 255f; skin[i] = px[x].g / 255f;
            }
        }

        static float Profile(float[] p, float u)
        {
            float f = Mathf.Clamp01(u) * (p.Length - 1);
            int i = Mathf.Min((int)f, p.Length - 2);
            return Mathf.Lerp(p[i], p[i + 1], f - i);
        }

        static float Smooth(float a, float b, float x) { float t = Mathf.Clamp01((x - a) / (b - a)); return t * t * (3f - 2f * t); }

        /// <summary>Lo mismo que Envelope() del shader: cola suelta, cuello firme, cabeza casi quieta.</summary>
        static float Envelope(float u)
        {
            if (u < 0.15f) return Mathf.Lerp(1.25f, 1.15f, u / 0.15f);
            if (u < 0.75f) return Mathf.Lerp(1.15f, 0.9f, (u - 0.15f) / 0.6f);
            if (u < 0.86f) return Mathf.Lerp(0.9f, 0.35f, (u - 0.75f) / 0.11f);
            return Mathf.Lerp(0.35f, 0.25f, (u - 0.86f) / 0.14f);
        }

        float nod;

        /// <summary>Corrimiento vertical (uv) que el shader le aplica al dragón en u: el ojo y las brasas lo siguen.</summary>
        float DragonWave(float u, float t)
        {
            float amp = WaveAmp * Envelope(Mathf.Clamp01(u)) * (1f + rageShown * 0.25f);
            float ph = u * spiritSize.x * WaveFreq + t * WaveSpeed;
            return Mathf.Sin(ph) * amp + Mathf.Sin(ph * 2.3f + 1.7f) * amp * 0.18f + nod * Smooth(0.80f, 0.98f, u);
        }

        /// <summary>Punto del dragón (u, v del marco) en coordenadas locales del cuerpo, con la ola aplicada.</summary>
        Vector2 DragonPoint(float u, float v, float t) => new Vector2(u * spiritSize.x, (v - DragonWave(u, t)) * spiritSize.y);

        public void SetObjective(string text)
        {
            text = string.IsNullOrEmpty(text) ? "" : text;
            if (text == objective) return;
            objective = text;
            if (objectiveRoutine != null) StopCoroutine(objectiveRoutine);
            objectiveRoutine = StartCoroutine(ObjectiveChange(text));
        }

        // el viejo se va subiendo y el nuevo se escribe con una raya dorada que se dibuja debajo
        IEnumerator ObjectiveChange(string text)
        {
            var rt = objectiveText.rectTransform;
            var basePos = new Vector2(-26, -38);
            if (!string.IsNullOrEmpty(objectiveText.text))
            {
                yield return UIAnim.Tween(0.25f, UIAnim.OutCubic, k => { objectiveText.alpha = 1f - k; rt.anchoredPosition = basePos + new Vector2(0f, 8f * k); });
            }
            objectiveText.text = text;
            objectiveText.alpha = 1f;
            rt.anchoredPosition = basePos;
            objectiveText.maxVisibleCharacters = 0;
            objectiveLine.fillAmount = 0f;
            float shown = 0f, t = 0f;
            while (shown < text.Length || t < 0.4f)
            {
                t += Time.unscaledDeltaTime;
                shown += Time.unscaledDeltaTime * 60f;
                objectiveText.maxVisibleCharacters = (int)shown;
                objectiveLine.fillAmount = UIAnim.OutCubic(t / 0.4f);
                yield return null;
            }
            objectiveText.maxVisibleCharacters = 99999;
            objectiveRoutine = null;
        }

        /// <summary>No alcanza el Espíritu (sin costo: el dash cansado todavía no está listo).</summary>
        public void DenySpirit() => spiritShake = 0.35f;

        /// <summary>No alcanza el Espíritu para algo que cuesta 'cost': además del sacudón, se raya en rojo lo que falta.</summary>
        public void DenySpirit(float cost)
        {
            spiritShake = 0.35f;
            var p = Game.Player;
            if (p == null) return;
            needValue = Mathf.Clamp01(cost / Mathf.Max(1f, p.config.maxSpirit));
            needA = 1f; needHold = 0.45f;
        }

        void UpdateHUD(float dt)
        {
            var p = Game.Player;
            if (p == null) { hudGroup.alpha = 0f; return; }
            bool hide = HideHud;
            hudGroup.alpha = 1f;
            leftGroup.alpha = Mathf.MoveTowards(leftGroup.alpha, hide ? 0f : 1f, dt * 4f);
            // en combate el HUD es solo la bandana y el dragón: sellos y objetivo (información para recorrer)
            // se apartan y vuelven al terminar la pelea. Los sellos siguen a la vista mientras vuela el que se
            // acaba de ganar (pasa en una cinemática)
            bool inCombat = Game.Combat != null && Game.Combat.InCombat;
            bool sealsShow = (!hide && !inCombat) || Time.unscaledTime < sealVisibleUntil;
            rightGroup.alpha = Mathf.MoveTowards(rightGroup.alpha, sealsShow ? 1f : 0f, dt * (sealsShow ? 2f : 4f));
            // el objetivo, además, espera a que se vaya el título de zona (antes competía con todo)
            bool objShow = !hide && objective.Length > 0 && !inCombat && titleGroup.alpha < 0.01f;
            objectiveGroup.alpha = Mathf.MoveTowards(objectiveGroup.alpha, objShow ? 1f : 0f, dt * (objShow ? 2f : 5f));
            float t = Time.unscaledTime;
            UpdateHealth(p, dt, t);
            UpdateDragon(p, dt, t);
            UpdateSeals(dt);
        }

        // ---------------------------------------------------------------- vida
        void UpdateHealth(PlayerController p, float dt, float t)
        {
            float hp = p.Health01;
            if (lastHealth < 0f) { lastHealth = hp; healthShown = hp; healthGhostValue = hp; }
            if (hp < lastHealth - 0.001f)
            {
                healthHit = 1f; healthFlash = 1f;
                healthGhostValue = Mathf.Max(healthGhostValue, healthShown); healthGhostHold = 0.45f;
            }
            else if (hp > lastHealth + 0.005f) { healX = -0.1f; healA = 1f; }   // se curó: brillo que recorre la banda
            lastHealth = hp;
            healthShown = Mathf.MoveTowards(healthShown, hp, dt * (hp < healthShown ? 4f : 1.2f));
            healthGhostHold -= dt;
            if (healthGhostHold <= 0f) healthGhostValue = Mathf.MoveTowards(healthGhostValue, healthShown, dt * 0.5f);
            if (healthGhostValue < healthShown) healthGhostValue = healthShown;
            healthHit = Mathf.MoveTowards(healthHit, 0f, dt * 3.5f);
            healthFlash = Mathf.MoveTowards(healthFlash, 0f, dt / 0.08f);
            if (healX < 1.3f) { healX += dt / 0.5f * 1.3f; healA = Mathf.MoveTowards(healA, 0f, dt * 1.2f); }
            // latido compartido (UIBeat): lub-dub que se acelera con menos vida
            UIBeat.Tick(dt, hp);
            float beat = UIBeat.Value;
            healthRoot.localScale = Vector3.one * (1f + beat * 0.035f + healthHit * 0.03f);
            healthRoot.anchoredPosition = HealthPos + new Vector2(Mathf.Sin(t * 83f), Mathf.Cos(t * 67f)) * 5f * healthHit * healthHit;
            if (healthFillMat != null)
            {
                SetBandana(healthFrameMat, beat, t);
                SetBandana(healthFillMat, beat, t);
            }
            else
            {
                healthFill.fillAmount = healthShown;
                if (healthFallbackGhost != null) healthFallbackGhost.fillAmount = healthGhostValue;
            }
        }

        void SetBandana(Material m, float beat, float t)
        {
            if (m == null) return;
            m.SetFloat(IdFill, healthShown); m.SetFloat(IdGhost, healthGhostValue); m.SetFloat(IdHit, healthHit); m.SetFloat(IdFlash, healthFlash);
            m.SetFloat(IdHeal, healX); m.SetFloat(IdHealA, healA); m.SetFloat(IdLow, beat); m.SetFloat(IdT, t);
        }

        // ---------------------------------------------------------------- espíritu + Filo de Ira
        void UpdateDragon(PlayerController p, float dt, float t)
        {
            float sp = p.Spirit01;
            if (lastSpirit < 0f) { lastSpirit = sp; spiritShown = sp; spiritGhostValue = sp; }
            if (sp < lastSpirit - 0.001f)
            {
                spiritGhostValue = Mathf.Max(spiritGhostValue, spiritShown); spiritGhostHold = 0.3f; spiritGhostAge = 0f;
            }
            else if (sp > lastSpirit + 0.001f)
            {
                spiritPulse = Mathf.Max(spiritPulse, Mathf.Clamp01(0.35f + (sp - lastSpirit) * 5f));
                // destello al pasar cada umbral útil: ya alcanza para el dash, el remate, una habilidad
                float max = Mathf.Max(1f, p.config.maxSpirit);
                CheckThreshold(lastSpirit, sp, p.config.dashCost / max);
                CheckThreshold(lastSpirit, sp, p.config.finisherCost / max);
                CheckThreshold(lastSpirit, sp, Mathf.Max(p.config.windSlashCost, p.config.whirlwindCost) / max);
            }
            lastSpirit = sp;
            spiritShown = Mathf.MoveTowards(spiritShown, sp, dt * (sp < spiritShown ? 5f : 1.4f));
            spiritGhostHold -= dt;
            if (spiritGhostHold <= 0f) { spiritGhostValue = Mathf.MoveTowards(spiritGhostValue, spiritShown, dt * 0.55f); spiritGhostAge = Mathf.MoveTowards(spiritGhostAge, 1f, dt * 1.4f); }
            if (spiritGhostValue < spiritShown) spiritGhostValue = spiritShown;
            spiritPulse = Mathf.MoveTowards(spiritPulse, 0f, dt * 2.2f);
            spiritShake = Mathf.MoveTowards(spiritShake, 0f, dt);
            sparkA = Mathf.MoveTowards(sparkA, 0f, dt * 1.8f);
            needHold -= dt;
            if (needHold <= 0f) needA = Mathf.MoveTowards(needA, 0f, dt / 0.25f);

            // Filo de Ira: el mismo valor es la carga (llenándose) y el tiempo que queda (activo, lo vacía el temporizador)
            float rage01 = p.Rage01;
            bool active = p.RageActive;
            bool ready = !active && rage01 >= 0.85f;
            rageShown = Mathf.MoveTowards(rageShown, active ? 1f : 0f, dt * 2.5f);
            readyShown = Mathf.MoveTowards(readyShown, ready ? 1f : 0f, dt * 3f);
            rageFrontShown = rage01 > rageFrontShown ? Mathf.MoveTowards(rageFrontShown, rage01, dt * 1.6f) : rage01;
            dimShown = Mathf.MoveTowards(dimShown, p.DashTired ? 1f : 0f, dt * 3f);
            if (active && !wasRageActive) Roar();
            if (active && rage01 > lastRage01 + 0.004f) Flare(rage01, t);   // pegando estira el Filo: el frente brilla
            wasRageActive = active;
            lastRage01 = rage01;

            // respira (4 s) y cabecea; el rugido lo agranda y lo inclina un instante
            roar = Mathf.MoveTowards(roar, 1f, dt / 0.35f);
            float roarK = 1f - UIAnim.OutBack(roar, 1.6f);
            float breath = Mathf.Sin(t * Mathf.PI * 0.5f);
            nod = 0.014f * Mathf.Sin(t * Mathf.PI * 0.5f + 1.1f) * (1f - 0.5f * rageShown) + 0.03f * Mathf.Max(0f, roarK);
            spiritRoot.anchoredPosition = SpiritPos + new Vector2(Mathf.Sin(t * 70f) * 10f * spiritShake, 0f);
            spiritBody.localScale = Vector3.one * (1f + 0.012f * breath + 0.045f * spiritPulse * spiritPulse + 0.12f * roarK);
            spiritBody.localRotation = Quaternion.Euler(0f, 0f, -3f * roarK);

            if (spiritFillMat != null)
            {
                SetDragon(spiritFrameMat, t);
                SetDragon(spiritFillMat, t);
            }
            else
            {
                spiritFill.fillAmount = spiritShown;
                spiritFill.color = spiritShake > 0f ? Color.Lerp(Color.white, new Color(1f, 0.3f, 0.3f), spiritShake * 2f) : Color.white;
            }
            UpdateEye(p, dt, t);
            UpdateEmbers(dt, t);
        }

        void CheckThreshold(float before, float after, float th)
        {
            if (before < th && after >= th) { sparkA = 1f; sparkX = th; SparkleAt(th, 6, Time.unscaledTime); }
        }

        void SetDragon(Material m, float t)
        {
            if (m == null) return;
            m.SetFloat(IdFill, spiritShown); m.SetFloat(IdGhost, spiritGhostValue); m.SetFloat(IdGhostAge, spiritGhostAge);
            m.SetFloat(IdNeed, Mathf.Max(needValue, spiritShown)); m.SetFloat(IdNeedA, needA);
            m.SetFloat(IdRageFront, rageFrontShown); m.SetFloat(IdReady, readyShown); m.SetFloat(IdRageOn, rageShown);
            m.SetFloat(IdPulse, spiritPulse); m.SetFloat(IdDeny, Mathf.Clamp01(spiritShake * 2.8f)); m.SetFloat(IdDim, dimShown);
            m.SetFloat(IdSpark, sparkA); m.SetFloat(IdSparkX, sparkX); m.SetFloat(IdNod, nod); m.SetFloat(IdT, t);
        }

        // ---------------------------------------------------------------- ojo
        // siempre abierto con su destello (antes, sin ira, no tenía ojo); parpadea cada 4-7 s, entrecierra sin
        // Espíritu para el dash (y cierra del todo mientras el dash cansado se recupera); con la ira arde
        void UpdateEye(PlayerController p, float dt, float t)
        {
            eyeRt.anchoredPosition = new Vector2(0f, -DragonWave(DragonEye.x, t) * spiritSize.y);
            eyeGlow.rectTransform.anchoredPosition = eyeRt.anchoredPosition;
            nextBlink -= dt;
            if (nextBlink <= 0f) { blinkT = 0f; nextBlink = Random.Range(4f, 7f); }
            blinkT += dt;
            float blink = blinkT < 0.12f ? 1f - 0.9f * Mathf.Sin(blinkT / 0.12f * Mathf.PI) : 1f;
            float lid = p.DashTired ? (p.TiredDashReadyIn > 0f ? 0.25f : 0.55f) : 1f;
            lidShown = Mathf.MoveTowards(lidShown, lid, dt * 4f);
            eyeRt.localScale = new Vector3(1f, Mathf.Max(0.1f, blink * lidShown), 1f);
            float fire = Mathf.Max(readyShown, rageShown);
            float flick = 0.8f + 0.2f * Mathf.PerlinNoise(t * 9f, 0.3f);
            var iris = Color.Lerp(EyeGold, new Color(1f, 0.4f, 0.08f), fire);
            iris = Color.Lerp(iris, new Color(0.62f, 0.5f, 0.3f), dimShown * 0.6f);
            eyeImg.color = iris;
            glintImg.color = new Color(1f, 1f, 0.92f, 0.95f * (1f - 0.5f * dimShown));
            eyeGlow.color = new Color(1f, 0.45f, 0.1f, fire * 0.85f * flick);
            eyeGlow.rectTransform.sizeDelta = Vector2.one * Mathf.Lerp(22f, 50f, Mathf.Max(rageShown, readyShown * 0.5f)) * flick;
        }

        // ---------------------------------------------------------------- brasas
        void Roar()
        {
            roar = 0f;
            float t = Time.unscaledTime;
            for (int i = 0; i < 30; i++) MouthEmber(t, 1.4f);
        }

        void Flare(float front, float t)
        {
            for (int i = 0; i < 8; i++)
            {
                float u = Mathf.Clamp01(front + Random.Range(-0.03f, 0.01f));
                var pos = DragonPoint(u, Profile(crest, u), t);
                SpawnEmber(pos, new Vector2(Random.Range(-40f, 40f), Random.Range(60f, 140f)), Random.Range(0.4f, 0.8f), Random.Range(8f, 15f), FireA, FireB, FireC);
            }
        }

        void SparkleAt(float fillX, int n, float t)
        {
            var c = Game.Content;
            float u = c != null ? c.spiritFillArea.x + fillX * c.spiritFillArea.width : fillX;
            for (int i = 0; i < n; i++)
            {
                var pos = DragonPoint(u, Mathf.Lerp(Profile(skin, u) - 0.25f, Profile(crest, u), Random.value), t);
                SpawnEmber(pos, Random.insideUnitCircle * 70f + new Vector2(0f, 40f), Random.Range(0.35f, 0.6f), Random.Range(6f, 11f), SparkA, SparkB, SparkB);
            }
        }

        void MouthEmber(float t, float force = 1f)
        {
            var pos = DragonPoint(DragonMouth.x, DragonMouth.y, t);
            SpawnEmber(pos, new Vector2(Random.Range(70f, 160f), Random.Range(-10f, 50f)) * force, Random.Range(0.35f, 0.65f), Random.Range(11f, 21f), FireA, FireB, FireC);
        }

        static readonly Color FireA = new Color(1f, 0.92f, 0.55f), FireB = new Color(1f, 0.5f, 0.12f), FireC = new Color(0.8f, 0.12f, 0.05f);
        static readonly Color SparkA = new Color(1f, 1f, 0.85f), SparkB = new Color(1f, 0.8f, 0.3f);

        void UpdateEmbers(float dt, float t)
        {
            if (emberRoot == null || UISprites.SoftDot == null) return;
            // brasas del lomo: muchas con el Filo activo, unas pocas lista para encenderse o casi llena
            float rate = rageShown * 24f + readyShown * 9f + (rageShown < 0.5f ? Mathf.Max(0f, rageFrontShown - 0.6f) * 8f : 0f);
            emberAcc += rate * dt;
            while (emberAcc >= 1f)
            {
                emberAcc -= 1f;
                float u = Random.Range(0.02f, Mathf.Max(0.05f, rageFrontShown));
                var pos = DragonPoint(u, Mathf.Lerp(Profile(skin, u), Profile(crest, u), Random.value), t);
                SpawnEmber(pos, new Vector2(Random.Range(-15f, 15f), Random.Range(45f, 100f)), Random.Range(0.55f, 1.05f), Random.Range(6f, 13f), FireA, FireB, FireC);
            }
            mouthAcc += rageShown * 10f * dt;
            while (mouthAcc >= 1f) { mouthAcc -= 1f; MouthEmber(t); }
            for (int i = 0; i < embers.Count; i++)
            {
                var e = embers[i];
                if (!e.img.enabled) continue;
                e.t += dt;
                float k = e.t / e.life;
                if (k >= 1f) { e.img.enabled = false; continue; }
                e.vel += new Vector2(Mathf.Sin(e.t * 7f + i) * 40f, 30f) * dt;
                e.rt.anchoredPosition += e.vel * dt;
                e.rt.sizeDelta = Vector2.one * e.size * (1f - k * 0.7f);
                var col = k < 0.4f ? Color.Lerp(e.c0, e.c1, k / 0.4f) : Color.Lerp(e.c1, e.c2, (k - 0.4f) / 0.6f);
                col.a = (k < 0.15f ? k / 0.15f : 1f - (k - 0.15f) / 0.85f) * 0.95f;
                e.img.color = col;
            }
        }

        void SpawnEmber(Vector2 pos, Vector2 vel, float life, float size, Color c0, Color c1, Color c2)
        {
            Ember e = null;
            foreach (var x in embers) if (!x.img.enabled) { e = x; break; }
            if (e == null)
            {
                if (embers.Count >= 64) return;
                var img = UIFactory.Centered("Ember", emberRoot, Color.clear, Vector2.zero, Vector2.zero, new Vector2(10, 10), UISprites.SoftDot);
                e = new Ember { rt = img.rectTransform, img = img };
                embers.Add(e);
            }
            e.img.enabled = true;
            e.rt.anchoredPosition = pos;
            e.t = 0f; e.life = life; e.size = size; e.vel = vel;
            e.c0 = c0; e.c1 = c1; e.c2 = c2;
        }

        // ---------------------------------------------------------------- sellos
        void UpdateSeals(float dt)
        {
            for (int i = 0; i < 3; i++)
            {
                bool has = Game.Save.HasSeal((SealId)i);
                // recién obtenido sin pasar por ShowSealObtained (o en otra partida cargada): golpe de sello igual
                if (has && !sealHad[i] && !sealFlying[i]) StampSeal(i);
                if (!has) sealHad[i] = false;
                bool shown = sealHad[i];
                sealPop[i] = Mathf.MoveTowards(sealPop[i], 0f, dt / 0.25f);
                float pop = sealPop[i];
                sealDiscs[i].color = shown ? Color.Lerp(SealGold, new Color(1f, 0.95f, 0.7f, 1f), pop) : UIFactory.Lacquer;
                sealIcons[i].color = shown ? SealIconHas : SealIconEmpty;
                sealDiscs[i].rectTransform.localScale = Vector3.one * (1f + 0.35f * pop * pop);
                // aro dorado que se abre
                sealRingT[i] += dt;
                float rk = sealRingT[i] / 0.5f;
                if (rk < 1f)
                {
                    sealRings[i].color = new Color(1f, 0.85f, 0.4f, 1f - rk);
                    sealRings[i].rectTransform.localScale = Vector3.one * Mathf.Lerp(1f, 2.2f, UIAnim.OutCubic(rk));
                }
                else if (sealRings[i].color.a > 0f) sealRings[i].color = new Color(1f, 0.85f, 0.4f, 0f);
            }
            // los tres: una raya dorada los une y laten uno detrás del otro
            if (sealLinkT >= 0f)
            {
                sealLinkT += dt;
                sealLink.fillAmount = UIAnim.OutCubic(sealLinkT / 0.5f);
                while (sealLinkPulsed < 3 && sealLinkT >= 0.15f * sealLinkPulsed) sealPop[sealLinkPulsed++] = 1f;
                if (sealLinkT > 0.8f) sealLinkT = -1f;
            }
        }

        readonly bool[] sealFlying = new bool[3];

        void StampSeal(int i)
        {
            sealHad[i] = true;
            sealPop[i] = 1f;
            sealRingT[i] = 0f;
            if (Game.Save.SealCount >= 3 && sealLink.fillAmount < 1f) { sealLinkT = 0f; sealLinkPulsed = 0; }
        }

        /// <summary>
        /// Se ganó un sello: el pictograma vuela del centro de la pantalla a su medallón, lo sella de un golpe
        /// (aro dorado) y arriba sale el aviso con su nombre ("Sello del Lago (2/3)", antes solo "Sello obtenido").
        /// </summary>
        public void ShowSealObtained(SealId seal)
        {
            ShowToast($"{UISprites.SealName(seal)} ({Game.Save.SealCount}/3)", UIFactory.Gold, 2.5f, UISprites.Get(UISprites.SealIconName(seal)));
            StartCoroutine(SealFly((int)seal));
        }

        IEnumerator SealFly(int i)
        {
            sealFlying[i] = true;
            sealVisibleUntil = Time.unscaledTime + 2.4f;
            var fly = UIFactory.Centered("SealFly", hudRight, UIFactory.Gold, new Vector2(0.5f, 0.5f), new Vector2(0f, 60f), new Vector2(150, 150), UISprites.Get(UISprites.SealIconName((SealId)i)));
            Vector2 from = new Vector2(0f, 60f);
            Vector2 to = hudRight.InverseTransformPoint(sealDiscs[i].rectTransform.position);
            Vector2 ctrl = new Vector2(Mathf.Lerp(from.x, to.x, 0.35f), Mathf.Max(from.y, to.y) + 220f);
            // aparece en el centro, espera un instante y vuela en arco
            yield return UIAnim.Tween(0.2f, UIAnim.OutCubic, k => fly.rectTransform.localScale = Vector3.one * Mathf.Lerp(0.4f, 1f, UIAnim.OutBack(k)));
            yield return new WaitForSecondsRealtime(0.25f);
            yield return UIAnim.Tween(0.6f, UIAnim.InOutSine, k =>
            {
                float a = 1f - k;
                fly.rectTransform.anchoredPosition = a * a * from + 2f * a * k * ctrl + k * k * to;
                fly.rectTransform.sizeDelta = Vector2.one * Mathf.Lerp(150f, 46f, k);
                fly.rectTransform.localRotation = Quaternion.Euler(0f, 0f, Mathf.Sin(k * Mathf.PI) * -18f);
            });
            Destroy(fly.gameObject);
            sealFlying[i] = false;
            StampSeal(i);
        }
    }
}
