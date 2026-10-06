using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace Nindo
{
    public struct DialogueLine
    {
        public string speaker;
        public string text;
        public DialogueLine(string speaker, string text) { this.speaker = speaker; this.text = text; }
    }

    /// <summary>
    /// Paneles con el estilo "Tinta y Bandana" (todo era un rectángulo plano): avisos de progreso en cola,
    /// título de zona con su sello rojo, consejo, diálogo con la cinta de quien habla, pausa y opciones con la
    /// columna de tinta y el logo del equipo, muerte con el tajo rojo y el final.
    /// </summary>
    public partial class UIManager
    {
        // ---- avisos de progreso (en el lugar del título de zona, en cola)
        struct Banner { public string text; public Color color; public float life; public Sprite icon; }
        readonly Queue<Banner> bannerQueue = new Queue<Banner>();
        RectTransform bannerRoot;
        CanvasGroup bannerGroup;
        Image bannerIcon;
        TextMeshProUGUI bannerText;
        float bannerT, bannerLife;
        bool bannerActive;

        // ---- título de zona
        CanvasGroup titleGroup;
        RectTransform titleRoot;
        Image titleSwash, titleStamp, titleRule;
        readonly Image[] titleSpecks = new Image[8];
        TextMeshProUGUI titleText, titleSub;
        Coroutine titleRoutine;

        // ---- consejo
        CanvasGroup tutorialGroup;
        RectTransform tutorialRoot;
        Image tutorialPanel;
        TextMeshProUGUI tutorialText;
        string tutorialRaw;
        int tutorialGlyphs = -1;
        bool tutorialVisible;
        float tutorialOpenT = 9f, tutorialHeight = 110f;

        // ---- diálogo
        CanvasGroup dialogueGroup;
        RectTransform dialogueRoot, speakerRibbonRt, dialogueHintRt;
        Image speakerRibbon, dialogueHint;
        TextMeshProUGUI dialogueSpeaker, dialogueText;
        bool lineComplete;
        float speakerSwipe = 1f, speakerWidth = 300f;
        public bool DialogueOpen { get; private set; }

        // ---- pausa / opciones / muerte / final
        GameObject pausePanel, optionsPanel, deathPanel, endPanel;
        Image pauseColumn, optionsColumn, pauseCardImg, optionsCardImg, deathDim, deathSwash;
        RectTransform pauseCard, optionsCard;
        CanvasGroup[] pauseItemGroups;
        Selectable pauseFirst, optionsFirst;
        float pauseOpenT = 9f, optionsOpenT = 9f;
        bool optionsFromPause;
        GameObject selectedBeforeOptions;
        CanvasGroup optionsBehind, deathGroup;
        TextMeshProUGUI deathTitle, deathSub;
        readonly List<(RectTransform row, Act act, bool alt)> controlKeys = new List<(RectTransform, Act, bool)>();
        RectTransform moveKey;
        int controlsVersion = -1;
        Image endLogo;
        CanvasGroup[] endLines;
        Selectable endButton;

        static readonly Color InkA = new Color(0.043f, 0.039f, 0.051f, 0.9f);

        void BuildPanels()
        {
            BuildBanner();
            BuildAreaTitle();
            BuildTutorial();
            BuildDialogue();
            BuildDeath();
            BuildPause();
            BuildOptions();
            BuildEnd();
        }

        // ================================================================== avisos de progreso
        void BuildBanner()
        {
            // debajo de la franja del HUD, en el lugar del título de zona (lo espera, así nunca compiten). Arriba,
            // a -170, un aviso largo tapaba la cabeza del dragón y el comienzo del objetivo
            bannerRoot = UIFactory.Rect("Banner", story, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0.5f, 0.5f), new Vector2(0, -300), new Vector2(900, 110));
            bannerGroup = bannerRoot.gameObject.AddComponent<CanvasGroup>();
            bannerGroup.alpha = 0f;
            var sw = UIFactory.Image("Swash", bannerRoot, new Color(0.043f, 0.039f, 0.051f, 0.86f), UISprites.BrushSwash);
            sw.rectTransform.Fill(new Vector2(-60f, -14f), new Vector2(60f, 14f));
            bannerIcon = UIFactory.Centered("Icon", bannerRoot, UIFactory.Gold, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(62, 62), null);
            bannerText = UIFactory.NoWrap(UIFactory.Text("Text", bannerRoot, "", 40, UIFactory.Gold, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(1100, 70), TextAlignmentOptions.Center, true));
            bannerText.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            UIFactory.Outline(bannerText, 0.2f);
        }

        /// <summary>
        /// Aviso de progreso ("Victoria", "Sello del Lago (2/3)", "Santuario... — partida guardada"): sobre un trazo
        /// de tinta debajo del HUD, en cola (antes uno pisaba al otro en el centro, encima de los enemigos) y
        /// esperando a que se vaya el título de zona. Los avisos de combate van pegados a Kaito: ShowCallout.
        /// </summary>
        public void ShowToast(string text, Color c, float life = 1.6f, Sprite icon = null)
        {
            if (string.IsNullOrEmpty(text)) return;
            if (bannerActive && bannerText.text == text) { bannerT = Mathf.Min(bannerT, 0.25f); return; }
            foreach (var b in bannerQueue) if (b.text == text) return;
            while (bannerQueue.Count >= 2) bannerQueue.Dequeue();   // como mucho dos esperando: los viejos ya no importan
            bannerQueue.Enqueue(new Banner { text = text, color = c, life = Mathf.Max(1.2f, life), icon = icon });
        }

        void UpdateBanner(float dt)
        {
            // con la muerte o el final lo pendiente ya no corresponde ("Victoria" después de reaparecer)
            if (deathPanel.activeSelf || endPanel.activeSelf)
            {
                bannerQueue.Clear();
                if (bannerActive) { bannerActive = false; bannerGroup.alpha = 0f; }
                return;
            }
            // en pausa (seguía animándose debajo) y mientras está el título de zona (va en el mismo lugar) el
            // aviso espera: se apaga rápido y, al volver, entra de nuevo con su tiempo entero
            if (PauseOpen || titleRoutine != null)
            {
                if (bannerActive) { bannerGroup.SetAlpha(Mathf.MoveTowards(bannerGroup.alpha, 0f, dt * 8f)); bannerT = 0f; }
                return;
            }
            if (!bannerActive)
            {
                if (bannerQueue.Count == 0) return;
                var b = bannerQueue.Dequeue();
                bannerActive = true; bannerT = 0f; bannerLife = b.life + 0.6f;
                bannerText.text = b.text; bannerText.color = b.color;
                float tw = bannerText.GetPreferredValues(b.text, 9999f, 70f).x;
                bannerIcon.sprite = b.icon;
                bannerIcon.enabled = b.icon != null;
                bannerIcon.color = b.color;
                float shift = b.icon != null ? 40f : 0f;
                bannerText.rectTransform.anchoredPosition = new Vector2(shift, 0f);
                bannerIcon.rectTransform.anchoredPosition = new Vector2(-tw * 0.5f - 44f + shift, 0f);
                bannerRoot.sizeDelta = new Vector2(Mathf.Max(640f, tw + 260f + shift * 2f), 110f);
            }
            bannerT += dt;
            // baja 40 px en 0.2 s, queda y se apaga en 0.4 s
            float a = bannerT < 0.2f ? UIAnim.OutCubic(bannerT / 0.2f) : bannerT > bannerLife - 0.4f ? Mathf.Clamp01((bannerLife - bannerT) / 0.4f) : 1f;
            bannerGroup.alpha = a;
            bannerRoot.anchoredPosition = new Vector2(0f, -260f - 40f * UIAnim.OutCubic(bannerT / 0.2f));
            if (bannerT >= bannerLife) { bannerActive = false; bannerGroup.alpha = 0f; }
        }

        // ================================================================== título de zona
        void BuildAreaTitle()
        {
            // arriba al centro, debajo del dragón y por encima de Kaito (antes en el centro: chocaba con "[E] Rezar..."
            // y el objetivo). El trazo cubre título, raya y subtítulo
            titleRoot = UIFactory.Rect("AreaTitle", story, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0.5f, 0.5f), new Vector2(0, -300), new Vector2(1400, 260));
            titleGroup = titleRoot.gameObject.AddComponent<CanvasGroup>();
            titleGroup.alpha = 0f;
            titleSwash = UIFactory.Centered("Swash", titleRoot, new Color(0.043f, 0.039f, 0.051f, 0.9f), new Vector2(0.5f, 0.5f), new Vector2(0, -18), new Vector2(1180, 200), UISprites.BrushSwash);
            titleSwash.type = Image.Type.Filled; titleSwash.fillMethod = Image.FillMethod.Horizontal; titleSwash.fillOrigin = 0;
            for (int i = 0; i < titleSpecks.Length; i++)
                titleSpecks[i] = UIFactory.Centered("Speck", titleRoot, new Color(0.7f, 0.07f, 0.1f, 0f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(10, 10), UISprites.SoftDot);
            titleStamp = UIFactory.Centered("Stamp", titleRoot, Color.white, new Vector2(0.5f, 0.5f), new Vector2(-480, 12), new Vector2(118, 118), null);
            titleText = UIFactory.NoWrap(UIFactory.Text("Title", titleRoot, "", 76, UIFactory.Paper, new Vector2(0.5f, 0.5f), new Vector2(0, 14), new Vector2(1300, 100), TextAlignmentOptions.Center, true));
            titleText.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            UIFactory.Outline(titleText, 0.2f);
            titleRule = UIFactory.Centered("Rule", titleRoot, new Color(UIFactory.Gold.r, UIFactory.Gold.g, UIFactory.Gold.b, 0.85f), new Vector2(0.5f, 0.5f), new Vector2(0, -38), new Vector2(560, 16), UISprites.BrushLine);
            titleRule.type = Image.Type.Filled; titleRule.fillMethod = Image.FillMethod.Horizontal; titleRule.fillOrigin = 0;
            titleSub = UIFactory.Text("Sub", titleRoot, "", 30, UIFactory.Gold, new Vector2(0.5f, 0.5f), new Vector2(0, -74), new Vector2(1200, 50), TextAlignmentOptions.Center);
            titleSub.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            UIFactory.Outline(titleSub, 0.2f);
        }

        /// <summary>Título de zona: el sello sale del lugar (Zone.Current), del jefe (si el título es el de un jefe) o la luna (prólogo).</summary>
        public void ShowAreaTitle(string title, string subtitle) => ShowAreaTitle(title, subtitle, ResolveStamp(title));

        /// <param name="stampIcon">Nombre del pictograma del sello rojo (ZoneLake, IconBoss...); null = sin sello.</param>
        public void ShowAreaTitle(string title, string subtitle, string stampIcon)
        {
            if (titleRoutine != null) StopCoroutine(titleRoutine);
            titleRoutine = StartCoroutine(AreaTitle(title, subtitle, UISprites.Hanko(stampIcon)));
        }

        static string ResolveStamp(string title)
        {
            var z = Zone.Current;
            if (z != null && z.title == title) return UISprites.ZoneIconName(z.id);
            if (Game.World != null)
                foreach (var a in Game.World.Arenas)
                    if (a != null && a.Boss != null && a.Boss.title == title) return "IconBoss";
            return title == "..." ? null : "ZoneMoon";
        }

        IEnumerator AreaTitle(string title, string subtitle, Sprite stamp)
        {
            titleText.text = title; titleSub.text = subtitle;
            // el ancho se mide con el espaciado final (4): antes se medía con el que tuviera el texto (0 en el
            // primer título de la partida) y, mientras las letras se juntan desde 18, el sello caía encima de las
            // primeras. TMP suma espaciado * tamaño / 100 por letra: el sello se corre con eso cada cuadro
            titleText.characterSpacing = 4f;
            float tw = titleText.GetPreferredValues(title, 9999f, 100f).x;
            float perSpacing = Mathf.Max(0, title.Length - 1) * titleText.fontSize * 0.01f;
            titleSwash.rectTransform.sizeDelta = new Vector2(Mathf.Clamp(tw + 420f, 900f, 1380f), 200f);
            titleStamp.sprite = stamp;
            titleStamp.enabled = false;
            titleRule.fillAmount = 0f; titleSub.alpha = 0f; titleText.alpha = 0f; titleSwash.fillAmount = 0f;
            Game.Audio?.Play("area_title", null, 0.7f);
            float t = 0f;
            bool thumped = false;
            while (t < 4.2f)
            {
                // en pausa el título espera escondido (seguía pintándose debajo del panel)
                if (PauseOpen) { titleGroup.alpha = 0f; yield return null; continue; }
                t += Time.unscaledDeltaTime;
                titleGroup.alpha = t > 3.6f ? 1f - (t - 3.6f) / 0.6f : 1f;
                // el trazo se pinta de izquierda a derecha, el nombre aparece y se junta
                titleSwash.fillAmount = UIAnim.OutCubic(t / 0.35f);
                titleText.alpha = Mathf.Clamp01((t - 0.1f) / 0.5f);
                float spacing = Mathf.Lerp(18f, 4f, UIAnim.OutCubic(t / 2.5f));
                titleText.characterSpacing = spacing;
                var stampPos = new Vector2(-(tw + (spacing - 4f) * perSpacing) * 0.5f - 96f, 10f);
                titleStamp.rectTransform.anchoredPosition = stampPos;
                // el sello cae de golpe a los 0.3 s y salpica tinta
                if (stamp != null && t >= 0.3f)
                {
                    if (!thumped) { thumped = true; titleStamp.enabled = true; ScatterSpecks(stampPos); }
                    float k = (t - 0.3f) / 0.12f;
                    titleStamp.rectTransform.localScale = Vector3.one * (k < 1f ? Mathf.Lerp(1.8f, 1f, UIAnim.InCubic(k)) : 1f);
                    titleStamp.rectTransform.localRotation = Quaternion.Euler(0, 0, -6f);
                    var sc = titleStamp.color; sc.a = Mathf.Clamp01(k * 2f); titleStamp.color = sc;
                }
                UpdateSpecks(t - 0.3f);
                titleRule.fillAmount = UIAnim.OutCubic((t - 0.6f) / 0.4f);
                titleSub.alpha = Mathf.Clamp01((t - 0.8f) / 0.4f);
                yield return null;
            }
            titleGroup.alpha = 0f;
            titleRoutine = null;
        }

        readonly Vector2[] speckVel = new Vector2[8];

        void ScatterSpecks(Vector2 at)
        {
            for (int i = 0; i < titleSpecks.Length; i++)
            {
                float a = (i / (float)titleSpecks.Length) * Mathf.PI * 2f + Random.Range(-0.3f, 0.3f);
                speckVel[i] = new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * Random.Range(140f, 260f);
                titleSpecks[i].rectTransform.anchoredPosition = at;
                titleSpecks[i].rectTransform.sizeDelta = Vector2.one * Random.Range(6f, 14f);
            }
        }

        void UpdateSpecks(float t)
        {
            for (int i = 0; i < titleSpecks.Length; i++)
            {
                var img = titleSpecks[i];
                if (t < 0f || t > 0.45f) { if (img.color.a > 0f) img.color = new Color(0.7f, 0.07f, 0.1f, 0f); continue; }
                img.rectTransform.anchoredPosition += speckVel[i] * Time.unscaledDeltaTime * (1f - t / 0.45f);
                img.color = new Color(0.7f, 0.07f, 0.1f, 0.9f * (1f - t / 0.45f));
            }
        }

        // ================================================================== consejo
        void BuildTutorial()
        {
            tutorialRoot = UIFactory.Rect("Tutorial", story, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0, 150), new Vector2(1100, 110));
            tutorialGroup = tutorialRoot.gameObject.AddComponent<CanvasGroup>();
            tutorialGroup.alpha = 0f;
            tutorialPanel = UIFactory.Sliced("Panel", tutorialRoot, UISprites.InkPanel, Color.white, 110f);
            var prt = tutorialPanel.rectTransform;
            prt.anchorMin = prt.anchorMax = new Vector2(0.5f, 0.5f); prt.pivot = new Vector2(0.5f, 0.5f); prt.sizeDelta = new Vector2(1100, 110);
            var lbl = UIFactory.Text("Label", tutorialRoot, "Consejo", 20, UIFactory.Gold, new Vector2(0f, 1f), new Vector2(120, -6), new Vector2(200, 26), TextAlignmentOptions.TopLeft, true);
            UIFactory.Outline(lbl, 0.15f);
            tutorialText = UIFactory.Text("Text", tutorialRoot, "", 34, UIFactory.Paper, TextAlignmentOptions.Center);
            tutorialText.rectTransform.Fill(new Vector2(120, 14), new Vector2(-120, -26));
        }

        /// <param name="text">Las teclas como "{Parry}" siguen al dispositivo mientras el consejo está a la vista.</param>
        public void ShowTutorial(string text)
        {
            if (!tutorialVisible || tutorialGroup.alpha < 0.05f) tutorialOpenT = 0f;
            tutorialVisible = true;
            if (text == tutorialRaw) return;
            tutorialRaw = text;
            RenderTutorial();
        }

        void RenderTutorial()
        {
            tutorialGlyphs = Game.Input != null ? Game.Input.GlyphVersion : -1;
            tutorialText.text = UIFactory.RichKeys(tutorialRaw);
            // el panel crece con el texto (los consejos largos de dos renglones se salían)
            tutorialHeight = Mathf.Max(110f, tutorialText.GetPreferredValues(tutorialText.text, 860f, 400f).y + 56f);
            tutorialRoot.sizeDelta = new Vector2(1100, tutorialHeight);
            tutorialPanel.rectTransform.SetSize(new Vector2(tutorialPanel.rectTransform.sizeDelta.x, tutorialHeight));
            // los extremos de pincel escalan con el alto (hasta 160: más alto ya no engorda las puntas)
            if (UISprites.InkPanel != null) tutorialPanel.pixelsPerUnitMultiplier = UISprites.InkPanel.rect.height / Mathf.Min(tutorialHeight, 160f);
        }

        public void HideTutorial() => tutorialVisible = false;

        void UpdateTutorial(float dt)
        {
            // agarró el mando (o volvió al teclado) con el consejo abierto: las teclas cambian con él
            if (tutorialRaw != null && Game.Input != null && Game.Input.GlyphVersion != tutorialGlyphs) RenderTutorial();
            // en pausa se aparta: el consejo del parry, justo cuando uno pausa a leer los controles, quedaba
            // debajo del velo y asomaba bajo la tarjeta de controles
            bool show = tutorialVisible && !DialogueOpen && !PauseOpen && !deathPanel.activeSelf && !endPanel.activeSelf;
            tutorialGroup.SetAlpha(Mathf.MoveTowards(tutorialGroup.alpha, show ? 1f : 0f, dt * 5f));
            // se desenrolla de 0 al ancho y el texto entra después (quieto, no se toca: no rehace el canvas)
            if (tutorialOpenT > 0.5f) return;
            tutorialOpenT += dt;
            float w = UIAnim.OutBack(tutorialOpenT / UIAnim.Medium);
            tutorialPanel.rectTransform.SetSize(new Vector2(Mathf.Max(260f, 1100f * w), tutorialHeight));
            tutorialText.alpha = Mathf.Clamp01((tutorialOpenT - 0.1f) / 0.15f);
        }

        // ================================================================== diálogo
        void BuildDialogue()
        {
            dialogueRoot = UIFactory.Rect("Dialogue", story, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0, 40), new Vector2(1300, 200));
            dialogueGroup = dialogueRoot.gameObject.AddComponent<CanvasGroup>();
            dialogueGroup.alpha = 0f;
            var panel = UIFactory.Sliced("Panel", dialogueRoot, UISprites.InkPanel, Color.white, 200f);
            panel.rectTransform.Fill(new Vector2(-40f, 0f), new Vector2(40f, 0f));
            // nombre sobre una pincelada de tinta (antes una cinta roja: se confundía con la bandana de la vida)
            speakerRibbon = UIFactory.Image("Swash", dialogueRoot, new Color(0.043f, 0.039f, 0.051f, 0.92f), UISprites.BrushSwash);
            speakerRibbonRt = speakerRibbon.rectTransform;
            Place(speakerRibbonRt, new Vector2(0f, 1f), new Vector2(-14f, 30f), new Vector2(320, 62));
            speakerRibbonRt.pivot = new Vector2(0f, 1f);
            // el nombre va aparte de la pincelada (no se aplasta mientras se pinta)
            dialogueSpeaker = UIFactory.NoWrap(UIFactory.Text("Speaker", dialogueRoot, "", 34, UIFactory.Paper, new Vector2(0f, 1f), new Vector2(92f, 0f), new Vector2(400, 50), TextAlignmentOptions.Left, true));
            dialogueSpeaker.rectTransform.pivot = new Vector2(0f, 0.5f);   // centrado en la cinta (que va de +30 a -32)
            UIFactory.Outline(dialogueSpeaker, 0.15f);
            var rule = UIFactory.Image("Rule", dialogueRoot, new Color(UIFactory.Gold.r, UIFactory.Gold.g, UIFactory.Gold.b, 0.7f), new Vector2(0f, 1f), new Vector2(84f, -40f), new Vector2(900, 12), UISprites.BrushLine);
            rule.rectTransform.pivot = new Vector2(0f, 0.5f);
            dialogueText = UIFactory.Text("Text", dialogueRoot, "", 36, UIFactory.Paper, new Vector2(0f, 1f), new Vector2(90f, -58f), new Vector2(1120, 130), TextAlignmentOptions.TopLeft);
            // avanzar: kunai que apunta para abajo y se mece, solo cuando la línea terminó de escribirse
            dialogueHint = UIFactory.Centered("Hint", dialogueRoot, UIFactory.Gold, new Vector2(1f, 0f), new Vector2(-64f, 34f), new Vector2(52, 18), UISprites.Kunai);
            dialogueHintRt = dialogueHint.rectTransform;
            dialogueHintRt.localRotation = Quaternion.Euler(0, 0, -90f);
        }

        /// <summary>Color del nombre de quien habla (claro, se lee sobre la tinta): Kaito dorado (su bandana amarilla),
        /// el abuelo índigo claro, Kage violeta, el clan carmesí.</summary>
        static Color SpeakerColor(string s)
        {
            if (s == StoryText.Kaito) return UIFactory.Gold;
            if (s == StoryText.Abuelo) return new Color(0.66f, 0.76f, 1f);
            if (s == StoryText.Kage) return new Color(0.8f, 0.64f, 1f);
            // el espíritu del abuelo (el dragón de la bandana): dorado pálido, aparte del dorado lleno de Kaito con quien
            // alterna líneas; con el carmesí del clan se leía como enemigo
            if (s == StoryText.Espiritu) return new Color(1f, 0.93f, 0.72f);
            return new Color(1f, 0.46f, 0.4f);
        }

        /// <summary>Muestra líneas de diálogo; se avanza con atacar/interactuar/confirmar.</summary>
        public IEnumerator Dialogue(IList<DialogueLine> lines)
        {
            DialogueOpen = true;
            var input = Game.Input;
            string lastSpeaker = null;
            for (int i = 0; i < lines.Count; i++)
            {
                if (lines[i].speaker != lastSpeaker)
                {
                    lastSpeaker = lines[i].speaker;
                    dialogueSpeaker.text = lastSpeaker;
                    dialogueSpeaker.color = SpeakerColor(lastSpeaker);
                    speakerWidth = Mathf.Max(300f, dialogueSpeaker.GetPreferredValues(lastSpeaker, 9999f, 50f).x + 160f);
                    speakerSwipe = 0f;
                }
                string raw = lines[i].text;
                int glyphs = -1, total = 0;
                // las teclas "{Attack}" se resuelven con el dispositivo de ahora y se rehacen si cambia a mitad de línea
                void Render()
                {
                    glyphs = input != null ? input.GlyphVersion : -1;
                    dialogueText.text = UIFactory.RichKeys(raw);
                    dialogueText.ForceMeshUpdate();
                    total = dialogueText.textInfo.characterCount;
                }
                dialogueText.maxVisibleCharacters = 0;
                Render();
                lineComplete = false;
                Game.Audio?.Play("dialogue", null, 0.4f);
                yield return null;
                // máquina de escribir a 48 letras por segundo, con un respiro en los puntos y las comas
                int shown = 0;
                float wait = 0f;
                while (shown < total)
                {
                    if (input != null && input.GlyphVersion != glyphs) { Render(); shown = Mathf.Min(shown, total); }
                    wait -= Time.unscaledDeltaTime;
                    while (wait <= 0f && shown < total)
                    {
                        char ch = dialogueText.textInfo.characterInfo[shown].character;
                        shown++;
                        wait += 1f / 48f + (ch == '.' || ch == '!' || ch == '?' || ch == '…' ? 0.16f : ch == ',' ? 0.07f : 0f);
                    }
                    dialogueText.maxVisibleCharacters = shown;
                    if (AdvancePressed(input)) shown = total;
                    yield return null;
                }
                dialogueText.maxVisibleCharacters = 99999;
                lineComplete = true;
                yield return null;
                while (!AdvancePressed(input))
                {
                    if (input != null && input.GlyphVersion != glyphs) { Render(); dialogueText.maxVisibleCharacters = 99999; }
                    yield return null;
                }
                Game.Audio?.Play("ui_move", null, 0.35f);
            }
            DialogueOpen = false;
            lineComplete = false;
            input?.ClearBuffer();
        }

        static bool AdvancePressed(InputReader input)
        {
            if (input == null) return true;
            return input.Pressed(Act.Attack) || input.Pressed(Act.Interact) || input.Pressed(Act.Submit) || input.Pressed(Act.Dash);
        }

        void UpdateDialogue(float dt)
        {
            // entra subiendo 24 px y apareciendo en 0.18 s
            dialogueGroup.SetAlpha(Mathf.MoveTowards(dialogueGroup.alpha, DialogueOpen ? 1f : 0f, dt / 0.18f));
            dialogueRoot.SetPos(new Vector2(0f, 40f - 24f * (1f - UIAnim.OutCubic(dialogueGroup.alpha))));
            if (speakerSwipe < 1f)
            {
                // con cada cambio de quien habla la pincelada se vuelve a pintar de izquierda a derecha
                speakerSwipe = Mathf.MoveTowards(speakerSwipe, 1f, dt / 0.2f);
                speakerRibbonRt.sizeDelta = new Vector2(Mathf.Lerp(110f, speakerWidth, UIAnim.OutBack(speakerSwipe)), 62f);
                dialogueSpeaker.alpha = Mathf.Clamp01((speakerSwipe - 0.4f) / 0.4f);
            }
            if (dialogueHint.enabled != lineComplete) dialogueHint.enabled = lineComplete;
            if (lineComplete) dialogueHintRt.anchoredPosition = new Vector2(-64f, 34f + 6f * Mathf.Sin(Time.unscaledTime * Mathf.PI * 2.8f));
        }

        // ================================================================== columna de tinta (pausa y opciones)
        Image MenuColumn(Transform parent, string title, out RectTransform titleRt)
        {
            var col = UIFactory.Image("Column", parent, new Color(0.035f, 0.03f, 0.04f, 0.96f), UISprites.BrushSwash);
            col.rectTransform.anchorMin = col.rectTransform.anchorMax = new Vector2(0f, 1f);
            col.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            col.rectTransform.localRotation = Quaternion.Euler(0, 0, -90f);   // la tinta se junta arriba y se seca abajo
            col.type = Image.Type.Filled; col.fillMethod = Image.FillMethod.Horizontal; col.fillOrigin = 0;
            var c = Game.LoadContent();
            if (c.logo != null)
            {
                var logo = UIFactory.Image("Logo", parent, UIFactory.Paper, new Vector2(0f, 1f), new Vector2(110, -90), new Vector2(330, 330f * c.logo.rect.height / c.logo.rect.width), c.logo);
                logo.preserveAspect = true;
            }
            else UIFactory.Text("Logo", parent, "NINDŌ", 90, UIFactory.Paper, new Vector2(0f, 1f), new Vector2(110, -90), new Vector2(400, 120), TextAlignmentOptions.TopLeft, true);
            var t = UIFactory.Text("Title", parent, title, 44, UIFactory.Gold, new Vector2(0f, 1f), new Vector2(118, -290), new Vector2(500, 60), TextAlignmentOptions.TopLeft, true);
            UIFactory.Outline(t, 0.15f);
            titleRt = t.rectTransform;
            return col;
        }

        void SizeColumn(Image col)
        {
            // rotada: su "ancho" es el alto de la pantalla (+ margen), sea 16:9, 4:3 o 21:9
            float h = root.rect.height + 240f;
            col.rectTransform.sizeDelta = new Vector2(h, 720f);
            col.rectTransform.anchoredPosition = new Vector2(300f, -root.rect.height * 0.5f);
        }

        static Button ColumnItem(Transform parent, string label, int index, UnityEngine.Events.UnityAction action)
        {
            var b = UIFactory.MenuItem(label, parent, label, new Vector2(470, 70), action, 39f);
            var rt = (RectTransform)b.transform;
            rt.anchorMin = rt.anchorMax = new Vector2(0f, 1f); rt.pivot = new Vector2(0f, 0.5f);
            rt.anchoredPosition = new Vector2(106f, -410f - index * 92f);
            return b;
        }

        // ================================================================== pausa
        void BuildPause()
        {
            var bg = UIFactory.Image("Pause", menus, new Color(0.01f, 0.01f, 0.03f, 0.55f));
            bg.rectTransform.Fill(Vector2.zero, Vector2.zero);
            bg.raycastTarget = true;
            pausePanel = bg.gameObject;
            pauseColumn = MenuColumn(bg.transform, "Pausa", out _);
            string[] labels = { "Continuar", "Opciones", "Volver al menú", "Salir del juego" };
            UnityEngine.Events.UnityAction[] actions = { () => SetPaused(false), () => OpenOptions(true), () => { SetPaused(false); SaveSystem.Save(); SceneFlow.LoadMenu(); }, Application.Quit };
            pauseItemGroups = new CanvasGroup[labels.Length];
            for (int i = 0; i < labels.Length; i++)
            {
                var b = ColumnItem(bg.transform, labels[i], i, actions[i]);
                pauseItemGroups[i] = b.gameObject.AddComponent<CanvasGroup>();
                if (i == 0) pauseFirst = b;
            }
            // tarjeta de controles: un renglón por acción con las teclas del dispositivo que se está usando
            var card = UIFactory.Sliced("Controls", bg.transform, UISprites.InkCard, Color.white, 256f);
            pauseCard = card.rectTransform;
            pauseCardImg = card;
            Place(pauseCard, new Vector2(0.5f, 0.5f), new Vector2(370f, -20f), new Vector2(860, 640));
            pauseCard.pivot = new Vector2(0.5f, 0.5f);
            card.pixelsPerUnitMultiplier = 1f;
            var ct = UIFactory.Text("Title", pauseCard, "Controles", 36, UIFactory.Gold, new Vector2(0f, 1f), new Vector2(100f, -66f), new Vector2(400, 50), TextAlignmentOptions.TopLeft, true);
            UIFactory.Outline(ct, 0.15f);
            (string label, Act act)[] rows =
            {
                ("Moverse", Act.Submit), ("Atacar", Act.Attack), ("Parry", Act.Parry), ("Esquivar (dash)", Act.Dash), ("Fijar objetivo", Act.Lock),
                ("Ejecutar", Act.Finisher), ("Habilidades", Act.Ability1), ("Interactuar", Act.Interact),
            };
            for (int i = 0; i < rows.Length; i++)
            {
                float y = -136f - i * 56f;
                UIFactory.Text("Row", pauseCard, rows[i].label, 28, UIFactory.Paper, new Vector2(0f, 1f), new Vector2(100f, y + 20f), new Vector2(300, 40), TextAlignmentOptions.Left);
                if (i == 0) { moveKey = UIFactory.KeyCap(pauseCard, "WASD", 44f, new Vector2(0f, 1f), new Vector2(420f, y)); continue; }
                controlKeys.Add((UIFactory.KeyCap(pauseCard, "?", 44f, new Vector2(0f, 1f), new Vector2(420f, y)), rows[i].act, false));
                controlKeys.Add((UIFactory.KeyCap(pauseCard, "?", 44f, new Vector2(0f, 1f), new Vector2(520f, y)), rows[i].act == Act.Ability1 ? Act.Ability2 : rows[i].act, rows[i].act != Act.Ability1));
            }
            pausePanel.SetActive(false);
        }

        /// <summary>Las teclas de la tarjeta de controles siguen al dispositivo (teclado, Xbox o PlayStation).</summary>
        void RefreshControls()
        {
            var input = Game.Input;
            if (input == null || controlsVersion == input.GlyphVersion) return;
            controlsVersion = input.GlyphVersion;
            float x = 0f;
            for (int i = 0; i < controlKeys.Count; i++)
            {
                var (key, act, alt) = controlKeys[i];
                string g = alt ? input.GlyphAlt(act) : input.Glyph(act);
                key.gameObject.SetActive(g != null);
                if (g == null) continue;
                UIFactory.SetKeyCap(key, g);
                // la segunda tecla va a continuación de la primera
                bool second = i % 2 == 1;
                float w = key.sizeDelta.x;
                if (!second) x = 400f;
                key.anchoredPosition = new Vector2(x + w * 0.5f, key.anchoredPosition.y);
                x += w + 14f;
            }
            UIFactory.SetKeyCap(moveKey, input.GlyphFamily == 0 ? "WASD" : "Stick izq.");
            moveKey.anchoredPosition = new Vector2(400f + moveKey.sizeDelta.x * 0.5f, moveKey.anchoredPosition.y);
        }

        public bool PauseOpen => pausePanel.activeSelf || optionsPanel.activeSelf;

        public void SetPaused(bool p)
        {
            // en cinemáticas no se pausa: sus esperas y planos corren en tiempo real y el diálogo
            // podía abrirse detrás del panel y avanzar con los clics del menú de pausa
            if (p && (DialogueOpen || Game.InCutscene || deathPanel.activeSelf || endPanel.activeSelf)) return;
            pausePanel.SetActive(p);
            optionsPanel.SetActive(false);
            Game.Time?.SetPaused(p);
            if (Game.Input != null)
            {
                Game.Input.GameplayBlocked = p || Game.InCutscene;
                // al reanudar se descarta el buffer: el clic en "Continuar" registra un ataque al bajar
                // el botón y la A del mando es Submit y Dash a la vez; no tienen que llegar al gameplay
                if (!p) Game.Input.ClearBuffer();
            }
            if (p)
            {
                pauseOpenT = 0f;
                SizeColumn(pauseColumn);
                RefreshControls();
                Select(pauseFirst);
            }
            Cursor.visible = p; Cursor.lockState = CursorLockMode.None;
            Game.Audio?.Play(p ? "ui_open" : "ui_close", null, 0.5f);
        }

        static void Select(Selectable s)
        {
            if (s == null || EventSystem.current == null) return;
            var item = s.GetComponent<NindoMenuItem>();
            if (item != null) item.silent = true;   // la primera selección al abrir no hace el ruido de "mover"
            EventSystem.current.SetSelectedGameObject(s.gameObject);
        }

        void UpdatePause(float dt)
        {
            if (!pausePanel.activeSelf) return;
            pauseOpenT += dt;
            // la columna se pinta en 0.18 s, los ítems entran de a uno (40 ms) y la tarjeta llega de la derecha
            pauseColumn.fillAmount = UIAnim.OutCubic(pauseOpenT / 0.18f);
            for (int i = 0; i < pauseItemGroups.Length; i++)
            {
                float k = UIAnim.OutCubic((pauseOpenT - 0.08f - i * 0.04f) / 0.16f);
                pauseItemGroups[i].alpha = k;
                var rt = (RectTransform)pauseItemGroups[i].transform;
                rt.anchoredPosition = new Vector2(106f - 24f * (1f - k), rt.anchoredPosition.y);
            }
            float ck = UIAnim.OutCubic((pauseOpenT - 0.1f) / 0.2f);
            pauseCard.anchoredPosition = new Vector2(370f + 120f * (1f - ck), -20f);
            pauseCardImg.color = new Color(1f, 1f, 1f, ck);
            RefreshControls();
        }

        // ================================================================== opciones
        void BuildOptions()
        {
            var bg = UIFactory.Image("Options", menus, new Color(0.01f, 0.01f, 0.03f, 0.7f));
            bg.rectTransform.Fill(Vector2.zero, Vector2.zero);
            bg.raycastTarget = true;
            optionsPanel = bg.gameObject;
            optionsColumn = MenuColumn(bg.transform, "Opciones", out _);
            var card = UIFactory.Sliced("Card", bg.transform, UISprites.InkCard, Color.white, 256f);
            optionsCard = card.rectTransform;
            optionsCardImg = card;
            card.pixelsPerUnitMultiplier = 1f;
            Place(optionsCard, new Vector2(0.5f, 0.5f), new Vector2(330f, -10f), new Vector2(1060, 860));
            optionsCard.pivot = new Vector2(0.5f, 0.5f);
            var rows = new List<Selectable>();
            var size = new Vector2(860, 62);
            void Row(Selectable s) => rows.Add(s);
            Row(UIFactory.OptionSlider("Master", optionsCard, "Volumen general", Settings.MasterVolume, v => Settings.MasterVolume = v, size));
            Row(UIFactory.OptionSlider("Music", optionsCard, "Música", Settings.MusicVolume, v => Settings.MusicVolume = v, size));
            Row(UIFactory.OptionSlider("Sfx", optionsCard, "Efectos", Settings.SfxVolume, v => Settings.SfxVolume = v, size));
            Row(UIFactory.OptionSlider("Shake", optionsCard, "Sacudida de cámara", Settings.ScreenShake, v => Settings.ScreenShake = v, size));
            Row(UIFactory.OptionSelector("SlowMo", optionsCard, "Cámara lenta", new[] { "Reducida", "Sí" }, Settings.SlowMotionEnabled ? 1 : 0, i => Settings.SlowMotionEnabled = i == 1, size));
            Row(UIFactory.OptionSelector("Rumble", optionsCard, "Vibración", new[] { "No", "Sí" }, Settings.Rumble ? 1 : 0, i => Settings.Rumble = i == 1, size));
            // solo las marcas sobre los enemigos ("!", escudo, rombo rojo): los anillos ensō y las zonas del piso
            // quedan siempre (son la lectura del golpe). Si el combate llega a usar Settings.ShowParryAids /
            // ShowUnblockableAids para los anillos, la opción puede volver a llamarse "Avisos de combate"
            Row(UIFactory.OptionSelector("Aids", optionsCard, "Marcas en enemigos", new[] { "Ninguna", "Solo imparables", "Todas" }, Settings.CombatAids, i => Settings.CombatAids = i, size));
            Row(UIFactory.OptionSelector("Fullscreen", optionsCard, "Pantalla completa", new[] { "No", "Sí" }, Screen.fullScreen ? 1 : 0, i => Settings.Fullscreen = i == 1, size));
            Row(UIFactory.OptionSelector("Quality", optionsCard, "Calidad", QualitySettings.names, QualitySettings.GetQualityLevel(), i => { QualitySettings.SetQualityLevel(i, true); Settings.Quality = i; }, size));
            var back = UIFactory.MenuItem("Back", optionsCard, "Volver", new Vector2(300, 66), CloseOptions, 36f);
            rows.Add(back);
            for (int i = 0; i < rows.Count; i++)
            {
                var rt = (RectTransform)rows[i].transform;
                rt.anchorMin = rt.anchorMax = new Vector2(0.5f, 1f); rt.pivot = new Vector2(0.5f, 0.5f);
                rt.anchoredPosition = new Vector2(i == rows.Count - 1 ? -280f : 20f, -96f - i * 70f - (i == rows.Count - 1 ? 16f : 0f));
                // navegación explícita arriba/abajo (izquierda/derecha cambian el valor)
                var nav = new Navigation { mode = Navigation.Mode.Explicit, selectOnUp = rows[(i + rows.Count - 1) % rows.Count], selectOnDown = rows[(i + 1) % rows.Count] };
                rows[i].navigation = nav;
            }
            optionsFirst = rows[0];
            optionsPanel.SetActive(false);
        }

        /// <param name="behind">Botones que quedan detrás (menú principal): se desactivan mientras está abierto,
        /// si no la navegación con teclado/mando saltaba a ellos (ocultos) y Enter podía salir o pisar la partida.</param>
        public void OpenOptions(bool fromPause, CanvasGroup behind = null)
        {
            selectedBeforeOptions = EventSystem.current != null ? EventSystem.current.currentSelectedGameObject : null;
            optionsFromPause = fromPause;
            optionsBehind = behind;
            if (behind != null) behind.interactable = false;
            pausePanel.SetActive(false);
            optionsPanel.SetActive(true);
            optionsOpenT = 0f;
            SizeColumn(optionsColumn);
            Select(optionsFirst);
        }

        void CloseOptions()
        {
            Settings.Save();
            optionsPanel.SetActive(false);
            if (optionsBehind != null) { optionsBehind.interactable = true; optionsBehind = null; }
            if (optionsFromPause) { pausePanel.SetActive(true); pauseOpenT = 0.5f; Select(pauseFirst); }
            // desde el menú: volver a seleccionar el botón de antes (si no, teclado/mando quedan sin foco)
            else if (selectedBeforeOptions != null && selectedBeforeOptions.activeInHierarchy) Select(selectedBeforeOptions.GetComponent<Selectable>());
        }

        void UpdateOptions(float dt)
        {
            if (!optionsPanel.activeSelf) return;
            optionsOpenT += dt;
            optionsColumn.fillAmount = UIAnim.OutCubic(optionsOpenT / 0.18f);
            float ck = UIAnim.OutCubic((optionsOpenT - 0.05f) / 0.2f);
            optionsCard.anchoredPosition = new Vector2(330f + 120f * (1f - ck), -10f);
            optionsCardImg.color = new Color(1f, 1f, 1f, ck);
        }

        // ================================================================== muerte
        void BuildDeath()
        {
            deathDim = UIFactory.Image("Death", story, new Color(0, 0, 0, 0f));
            deathDim.rectTransform.Fill(Vector2.zero, Vector2.zero);
            deathPanel = deathDim.gameObject;
            deathGroup = deathPanel.AddComponent<CanvasGroup>();
            // tajo de pincel rojo bandana (no una mancha de sangre)
            deathSwash = UIFactory.Centered("Slash", deathDim.transform, new Color(0.75f, 0.055f, 0.08f, 1f), new Vector2(0.5f, 0.5f), new Vector2(-20f, 30f), new Vector2(1500, 300), UISprites.BrushSwash);
            deathSwash.rectTransform.localRotation = Quaternion.Euler(0, 0, 4f);
            deathSwash.type = Image.Type.Filled; deathSwash.fillMethod = Image.FillMethod.Horizontal; deathSwash.fillOrigin = 0;
            deathTitle = UIFactory.NoWrap(UIFactory.Text("Text", deathDim.transform, "Caíste", 150, UIFactory.Paper, new Vector2(0.5f, 0.5f), new Vector2(-30f, 40f), new Vector2(1000, 200), TextAlignmentOptions.Center, true));
            deathTitle.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            UIFactory.Outline(deathTitle, 0.22f);
            deathSub = UIFactory.Text("Sub", deathDim.transform, "El camino ninja continúa desde el último santuario...", 34, UIFactory.Paper, new Vector2(0.5f, 0.5f), new Vector2(0, -150), new Vector2(1400, 60), TextAlignmentOptions.Center);
            deathSub.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            UIFactory.Outline(deathSub, 0.2f);
            deathPanel.SetActive(false);
        }

        public IEnumerator DeathScreen()
        {
            deathPanel.SetActive(true);
            deathGroup.alpha = 1f;
            float t = 0f;
            while (t < 1.2f)
            {
                t += Time.unscaledDeltaTime;
                deathDim.color = new Color(0, 0, 0, 0.7f * UIAnim.OutCubic(t / 0.5f));
                deathSwash.fillAmount = UIAnim.OutCubic(t / 0.22f);
                float k = (t - 0.08f) / 0.25f;
                deathTitle.alpha = Mathf.Clamp01(k * 2f);
                deathTitle.rectTransform.localScale = Vector3.one * Mathf.Lerp(1.25f, 1f, UIAnim.OutCubic(k));
                deathSub.alpha = Mathf.Clamp01((t - 0.6f) / 0.4f);
                yield return null;
            }
            yield return new WaitForSecondsRealtime(1.6f);
            yield return Fade(1f, 0.6f);
            deathPanel.SetActive(false);
        }

        // ================================================================== final
        void BuildEnd()
        {
            var bg = UIFactory.Image("End", menus, new Color(0, 0, 0, 0.96f));
            bg.rectTransform.Fill(Vector2.zero, Vector2.zero);
            bg.raycastTarget = true;
            endPanel = bg.gameObject;
            var c = Game.LoadContent();
            if (c.logo != null)
            {
                endLogo = UIFactory.Centered("Logo", bg.transform, UIFactory.Gold, new Vector2(0.5f, 0.5f), new Vector2(0, 300), new Vector2(700, 700f * c.logo.rect.height / c.logo.rect.width), c.logo);
                endLogo.preserveAspect = true;
            }
            else UIFactory.Text("Title", bg.transform, "NINDŌ", 120, UIFactory.Gold, new Vector2(0.5f, 0.5f), new Vector2(0, 300), new Vector2(1600, 180), TextAlignmentOptions.Center, true);
            string[] lines =
            {
                "Kaito rescató a su abuelo.",
                "El verdadero poder nace del lazo que nos une a los nuestros.",
                "<size=30><color=#e8c870>Un juego de</color></size>\nFelipe Doval  ·  Teo González  ·  Mateo Drault  ·  Pedro Henríquez",
                "<size=28>Gracias por jugar.</size>",
                // la OFL pide nombrar las fuentes (modificadas) y su licencia en lo que se distribuye
                "<size=20><color=#8a8070>Fuentes: Shippori Mincho B1 y Zen Maru Gothic (con macrones agregados) · SIL Open Font License 1.1</color></size>",
            };
            float[] ys = { 90f, 30f, -70f, -160f, -215f };
            endLines = new CanvasGroup[lines.Length];
            for (int i = 0; i < lines.Length; i++)
            {
                var t = UIFactory.Text("Line" + i, bg.transform, lines[i], i < 2 ? 40 : 34, UIFactory.Paper, new Vector2(0.5f, 0.5f), new Vector2(0, ys[i]), new Vector2(1600, i == 2 ? 100 : 56), TextAlignmentOptions.Center, i == 0);
                t.rectTransform.pivot = new Vector2(0.5f, 0.5f);
                endLines[i] = t.gameObject.AddComponent<CanvasGroup>();
            }
            var b = UIFactory.MenuItem("Menu", bg.transform, "Volver al menú", new Vector2(420, 70), () => SceneFlow.LoadMenu(), 36f, TextAlignmentOptions.Center);
            ((RectTransform)b.transform).anchoredPosition = new Vector2(0, -360);
            endButton = b;
            endPanel.SetActive(false);
        }

        public void ShowEnding()
        {
            endPanel.SetActive(true);
            // la cinemática del final ya devolvió el control: el clic o la A que adelantan los renglones hacían
            // atacar o esquivar a Kaito detrás del panel (con su sonido). El botón del menú no usa el buffer
            if (Game.Input != null) Game.Input.GameplayBlocked = true;
            StartCoroutine(EndingReveal());
            Cursor.visible = true;
        }

        // el logo en oro y después cada renglón, de a uno; el botón al final (no se saltea el cierre sin querer,
        // pero confirmar lo completa de una)
        IEnumerator EndingReveal()
        {
            foreach (var g in endLines) g.alpha = 0f;
            endButton.gameObject.SetActive(false);
            if (endLogo != null) endLogo.color = new Color(UIFactory.Gold.r, UIFactory.Gold.g, UIFactory.Gold.b, 0f);
            float t = 0f, total = 1.2f * (endLines.Length + 1);
            yield return null;
            while (t < total)
            {
                t += Time.unscaledDeltaTime;
                if (AdvancePressed(Game.Input)) t = total;
                if (endLogo != null) endLogo.color = new Color(UIFactory.Gold.r, UIFactory.Gold.g, UIFactory.Gold.b, UIAnim.InOutSine(t / 1.2f));
                for (int i = 0; i < endLines.Length; i++) endLines[i].alpha = UIAnim.InOutSine((t - 1.2f * (i + 1)) / 1.2f);
                yield return null;
            }
            endButton.gameObject.SetActive(true);
            Game.Input?.ClearBuffer();
            Select(endButton);
        }

        // ================================================================== update
        void UpdatePanels(float dt)
        {
            UpdateBanner(dt);
            UpdateTutorial(dt);
            UpdateDialogue(dt);
            UpdatePause(dt);
            UpdateOptions(dt);

            var input = Game.Input;
            if (input != null && input.Pressed(Act.Pause) && SceneManager.GetActiveScene().name != "Menu")
            {
                if (optionsPanel.activeSelf) CloseOptions();
                else if (!endPanel.activeSelf && !deathPanel.activeSelf) SetPaused(!pausePanel.activeSelf);
            }
            else if (input != null && input.Pressed(Act.Cancel) && optionsPanel.activeSelf) CloseOptions();
        }
    }
}
