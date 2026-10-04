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

    public partial class UIManager
    {
        // toasts / títulos / tutorial / diálogo
        TextMeshProUGUI toast;
        float toastT, toastLife;
        CanvasGroup titleGroup;
        TextMeshProUGUI titleText, titleSub, titleKanji;
        Coroutine titleRoutine;
        CanvasGroup tutorialGroup;
        TextMeshProUGUI tutorialText;
        bool tutorialVisible;
        CanvasGroup dialogueGroup;
        TextMeshProUGUI dialogueSpeaker, dialogueText, dialogueHint;
        public bool DialogueOpen { get; private set; }

        // pausa / opciones / muerte / final
        GameObject pausePanel, optionsPanel, deathPanel, endPanel;
        CanvasGroup deathGroup;
        Button pauseFirst, optionsFirst;
        bool optionsFromPause;

        void BuildPanels()
        {
            toast = UIFactory.Text("Toast", overlay, "", 54, UIFactory.Gold, new Vector2(0.5f, 0.5f), new Vector2(0, 220), new Vector2(1200, 90), TextAlignmentOptions.Center, true);
            UIFactory.Outline(toast, 0.3f);
            toast.alpha = 0f;

            // título de zona
            var tr = UIFactory.Rect("AreaTitle", overlay, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 260), new Vector2(1400, 260));
            titleGroup = tr.gameObject.AddComponent<CanvasGroup>(); titleGroup.alpha = 0f;
            var stroke = UIFactory.Image("Stroke", tr, new Color(0.04f, 0.03f, 0.05f, 0.65f), new Vector2(0.5f, 0.5f), new Vector2(0, -10), new Vector2(1100, 120));
            titleKanji = UIFactory.Text("Kanji", tr, "", 110, new Color(0.75f, 0.15f, 0.12f, 0.55f), new Vector2(0.5f, 0.5f), new Vector2(-470, 0), new Vector2(240, 240), TextAlignmentOptions.Center, true);
            titleText = UIFactory.Text("Title", tr, "", 76, UIFactory.Paper, new Vector2(0.5f, 0.5f), new Vector2(0, 0), new Vector2(1200, 100), TextAlignmentOptions.Center, true);
            UIFactory.Outline(titleText, 0.2f);
            titleSub = UIFactory.Text("Sub", tr, "", 30, UIFactory.Gold, new Vector2(0.5f, 0.5f), new Vector2(0, -62), new Vector2(1200, 50), TextAlignmentOptions.Center);
            UIFactory.Outline(titleSub, 0.2f);

            // tutorial
            var tut = UIFactory.Image("Tutorial", overlay, UIFactory.Panel, new Vector2(0.5f, 0f), new Vector2(0, 230), new Vector2(980, 120));
            tutorialGroup = tut.gameObject.AddComponent<CanvasGroup>(); tutorialGroup.alpha = 0f;
            tutorialText = UIFactory.Text("Text", tut.transform, "", 38, UIFactory.Paper, TextAlignmentOptions.Center);
            tutorialText.rectTransform.Fill(new Vector2(24, 10), new Vector2(-24, -10));

            // diálogo
            var dlg = UIFactory.Image("Dialogue", overlay, UIFactory.Panel, new Vector2(0.5f, 0f), new Vector2(0, 40), new Vector2(1300, 230));
            dialogueGroup = dlg.gameObject.AddComponent<CanvasGroup>(); dialogueGroup.alpha = 0f;
            var border = UIFactory.Image("Border", dlg.transform, new Color(0.85f, 0.65f, 0.25f, 0.8f));
            border.rectTransform.anchorMin = new Vector2(0, 1); border.rectTransform.anchorMax = new Vector2(1, 1); border.rectTransform.sizeDelta = new Vector2(0, 4); border.rectTransform.anchoredPosition = Vector2.zero;
            dialogueSpeaker = UIFactory.Text("Speaker", dlg.transform, "", 36, UIFactory.Gold, new Vector2(0, 1), new Vector2(40, -16), new Vector2(800, 50), TextAlignmentOptions.TopLeft, true);
            dialogueText = UIFactory.Text("Text", dlg.transform, "", 36, UIFactory.Paper, new Vector2(0, 1), new Vector2(40, -70), new Vector2(1220, 140), TextAlignmentOptions.TopLeft);
            dialogueHint = UIFactory.Text("Hint", dlg.transform, "▼", 26, UIFactory.Gold, new Vector2(1, 0), new Vector2(-30, 16), new Vector2(60, 40), TextAlignmentOptions.Center);

            BuildPause();
            BuildOptions();
            BuildDeath();
            BuildEnd();
        }

        // ================================================================== toasts / títulos
        public void ShowToast(string text, Color c, float life = 1.6f)
        {
            toast.text = text; toast.color = c; toastT = 0f; toastLife = life;
        }

        public void ShowAreaTitle(string title, string subtitle, string kanji = "")
        {
            if (titleRoutine != null) StopCoroutine(titleRoutine);
            titleRoutine = StartCoroutine(AreaTitle(title, subtitle, kanji));
        }

        IEnumerator AreaTitle(string title, string subtitle, string kanji)
        {
            titleText.text = title; titleSub.text = subtitle; titleKanji.text = kanji;
            Game.Audio?.Play("area_title", null, 0.7f);
            float t = 0f;
            while (t < 4.2f)
            {
                t += Time.unscaledDeltaTime;
                float a = t < 0.8f ? t / 0.8f : (t > 3.2f ? 1f - (t - 3.2f) : 1f);
                titleGroup.alpha = Mathf.Clamp01(a);
                titleText.characterSpacing = Mathf.Lerp(18f, 4f, Mathf.Clamp01(t / 2.5f));
                yield return null;
            }
            titleGroup.alpha = 0f;
        }

        // ================================================================== tutorial
        public void ShowTutorial(string text)
        {
            tutorialText.text = text; tutorialVisible = true;
        }

        public void HideTutorial() => tutorialVisible = false;

        // ================================================================== diálogo
        /// <summary>Muestra líneas de diálogo; se avanza con atacar/interactuar/confirmar.</summary>
        public IEnumerator Dialogue(IList<DialogueLine> lines)
        {
            DialogueOpen = true;
            var input = Game.Input;
            for (int i = 0; i < lines.Count; i++)
            {
                dialogueSpeaker.text = lines[i].speaker;
                dialogueText.text = lines[i].text;
                dialogueText.maxVisibleCharacters = 0;
                int total = lines[i].text.Length;
                float shown = 0f;
                Game.Audio?.Play("dialogue", null, 0.4f);
                yield return null;
                while (shown < total)
                {
                    shown += Time.unscaledDeltaTime * 48f;
                    dialogueText.maxVisibleCharacters = (int)shown;
                    if (AdvancePressed(input)) shown = total;
                    yield return null;
                }
                dialogueText.maxVisibleCharacters = 99999;
                yield return null;
                while (!AdvancePressed(input)) yield return null;
                Game.Audio?.Play("ui_move", null, 0.35f);
            }
            DialogueOpen = false;
            input?.ClearBuffer();
        }

        static bool AdvancePressed(InputReader input)
        {
            if (input == null) return true;
            return input.Pressed(Act.Attack) || input.Pressed(Act.Interact) || input.Pressed(Act.Submit) || input.Pressed(Act.Dash);
        }

        // ================================================================== pausa / opciones
        void BuildPause()
        {
            var bg = UIFactory.Image("Pause", overlay, new Color(0.02f, 0.02f, 0.05f, 0.82f));
            bg.rectTransform.Fill(Vector2.zero, Vector2.zero);
            bg.raycastTarget = true;
            pausePanel = bg.gameObject;
            var title = UIFactory.Text("Title", bg.transform, "忍道  Pausa", 80, UIFactory.Paper, new Vector2(0.5f, 0.5f), new Vector2(0, 290), new Vector2(1000, 120), TextAlignmentOptions.Center, true);
            UIFactory.Outline(title);
            string[] labels = { "Continuar", "Opciones", "Volver al menú", "Salir del juego" };
            UnityEngine.Events.UnityAction[] actions = { () => SetPaused(false), () => OpenOptions(true), () => { SetPaused(false); SaveSystem.Save(); SceneFlow.LoadMenu(); }, Application.Quit };
            for (int i = 0; i < labels.Length; i++)
            {
                var b = UIFactory.Button(labels[i], bg.transform, labels[i], new Vector2(520, 76), actions[i]);
                b.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, 120 - i * 96);
                if (i == 0) pauseFirst = b;
            }
            var hint = UIFactory.Text("Controls", bg.transform, ControlsText(), 24, new Color(1, 1, 1, 0.6f), new Vector2(0.5f, 0f), new Vector2(0, 40), new Vector2(1700, 120), TextAlignmentOptions.Center);
            pausePanel.SetActive(false);
        }

        static string ControlsText()
        {
            return "Mover: WASD / stick  ·  Atacar: Click izq / J / □  ·  Parry: Click der / K / L1  ·  Dash: Espacio / ○  ·  Fijar: Q / R3\n" +
                   "Ejecutar: F / △  ·  Habilidades del Espíritu: 1 y 2 / R2 y L2  ·  Interactuar: E / △  ·  Pausa: Esc / Start";
        }

        void BuildOptions()
        {
            var bg = UIFactory.Image("Options", overlay, new Color(0.02f, 0.02f, 0.05f, 0.9f));
            bg.rectTransform.Fill(Vector2.zero, Vector2.zero);
            bg.raycastTarget = true;
            optionsPanel = bg.gameObject;
            UIFactory.Text("Title", bg.transform, "Opciones", 70, UIFactory.Paper, new Vector2(0.5f, 0.5f), new Vector2(0, 330), new Vector2(800, 100), TextAlignmentOptions.Center, true);
            var items = new (string, float, UnityEngine.Events.UnityAction<float>)[]
            {
                ("Volumen general", Settings.MasterVolume, v => Settings.MasterVolume = v),
                ("Música", Settings.MusicVolume, v => Settings.MusicVolume = v),
                ("Efectos", Settings.SfxVolume, v => Settings.SfxVolume = v),
                ("Sacudida de cámara", Settings.ScreenShake, v => Settings.ScreenShake = v),
            };
            for (int i = 0; i < items.Length; i++)
            {
                var s = UIFactory.Slider(items[i].Item1, bg.transform, items[i].Item1, items[i].Item2, items[i].Item3);
                s.transform.parent.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, 200 - i * 78);
            }
            var slow = UIFactory.Button("SlowMo", bg.transform, SlowLabel(), new Vector2(620, 64), null);
            slow.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, -130);
            slow.onClick.AddListener(() => { Settings.SlowMotionEnabled = !Settings.SlowMotionEnabled; slow.GetComponentInChildren<TextMeshProUGUI>().text = SlowLabel(); });
            var full = UIFactory.Button("Fullscreen", bg.transform, FullLabel(), new Vector2(620, 64), null);
            full.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, -206);
            full.onClick.AddListener(() => { Settings.Fullscreen = !Settings.Fullscreen; full.GetComponentInChildren<TextMeshProUGUI>().text = FullLabel(!Screen.fullScreen); });
            var quality = UIFactory.Button("Quality", bg.transform, QualityLabel(), new Vector2(620, 64), null);
            quality.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, -282);
            quality.onClick.AddListener(() =>
            {
                int q = (QualitySettings.GetQualityLevel() + 1) % QualitySettings.names.Length;
                QualitySettings.SetQualityLevel(q, true); Settings.Quality = q;
                quality.GetComponentInChildren<TextMeshProUGUI>().text = QualityLabel();
            });
            var back = UIFactory.Button("Back", bg.transform, "Volver", new Vector2(420, 70), CloseOptions);
            back.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, -380);
            optionsFirst = slow;
            optionsPanel.SetActive(false);
        }

        static string SlowLabel() => "Cámara lenta: " + (Settings.SlowMotionEnabled ? "Sí" : "Reducida");
        static string FullLabel(bool? v = null) => "Pantalla completa: " + ((v ?? Screen.fullScreen) ? "Sí" : "No");
        static string QualityLabel() => "Calidad: " + QualitySettings.names[QualitySettings.GetQualityLevel()];

        public void OpenOptions(bool fromPause)
        {
            optionsFromPause = fromPause;
            pausePanel.SetActive(false);
            optionsPanel.SetActive(true);
            EventSystem.current?.SetSelectedGameObject(optionsFirst.gameObject);
        }

        void CloseOptions()
        {
            Settings.Save();
            optionsPanel.SetActive(false);
            if (optionsFromPause) { pausePanel.SetActive(true); EventSystem.current?.SetSelectedGameObject(pauseFirst.gameObject); }
        }

        public bool PauseOpen => pausePanel.activeSelf || optionsPanel.activeSelf;

        public void SetPaused(bool p)
        {
            if (p && (DialogueOpen || deathPanel.activeSelf || endPanel.activeSelf)) return;
            pausePanel.SetActive(p);
            optionsPanel.SetActive(false);
            Game.Time?.SetPaused(p);
            if (Game.Input != null) Game.Input.GameplayBlocked = p || Game.InCutscene;
            if (p) EventSystem.current?.SetSelectedGameObject(pauseFirst.gameObject);
            Cursor.visible = p; Cursor.lockState = CursorLockMode.None;
            Game.Audio?.Play(p ? "ui_open" : "ui_close", null, 0.5f);
        }

        // ================================================================== muerte / final
        void BuildDeath()
        {
            var bg = UIFactory.Image("Death", overlay, new Color(0, 0, 0, 0f));
            bg.rectTransform.Fill(Vector2.zero, Vector2.zero);
            deathPanel = bg.gameObject;
            deathGroup = deathPanel.AddComponent<CanvasGroup>();
            var t = UIFactory.Text("Text", bg.transform, "死  Caíste", 110, new Color(0.85f, 0.15f, 0.12f), new Vector2(0.5f, 0.5f), new Vector2(0, 40), new Vector2(1400, 160), TextAlignmentOptions.Center, true);
            UIFactory.Outline(t, 0.25f);
            UIFactory.Text("Sub", bg.transform, "El camino ninja continúa desde el último santuario...", 34, UIFactory.Paper, new Vector2(0.5f, 0.5f), new Vector2(0, -70), new Vector2(1400, 60), TextAlignmentOptions.Center);
            deathPanel.SetActive(false);
        }

        public IEnumerator DeathScreen()
        {
            deathPanel.SetActive(true);
            float t = 0f;
            while (t < 1.2f) { t += Time.unscaledDeltaTime; deathGroup.alpha = t / 1.2f; deathPanel.GetComponent<Image>().color = new Color(0, 0, 0, 0.75f * t / 1.2f); yield return null; }
            yield return new WaitForSecondsRealtime(1.6f);
            yield return Fade(1f, 0.6f);
            deathPanel.SetActive(false);
        }

        void BuildEnd()
        {
            var bg = UIFactory.Image("End", overlay, new Color(0, 0, 0, 0.95f));
            bg.rectTransform.Fill(Vector2.zero, Vector2.zero);
            bg.raycastTarget = true;
            endPanel = bg.gameObject;
            UIFactory.Text("Title", bg.transform, "忍道  NINDŌ", 120, UIFactory.Gold, new Vector2(0.5f, 0.5f), new Vector2(0, 240), new Vector2(1600, 180), TextAlignmentOptions.Center, true);
            UIFactory.Text("Body", bg.transform,
                "Kaito rescató a su abuelo.\nEl verdadero poder nace del lazo que nos une a los nuestros.\n\n" +
                "<size=30><color=#e8c870>Un juego de</color></size>\nFelipe Doval  ·  Teo González  ·  Mateo Drault  ·  Pedro Henríquez\n\n<size=26>Gracias por jugar.</size>",
                40, UIFactory.Paper, new Vector2(0.5f, 0.5f), new Vector2(0, -80), new Vector2(1600, 420), TextAlignmentOptions.Center);
            var b = UIFactory.Button("Menu", bg.transform, "Volver al menú", new Vector2(460, 74), () => SceneFlow.LoadMenu());
            b.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, -400);
            endPanel.SetActive(false);
        }

        public void ShowEnding()
        {
            endPanel.SetActive(true);
            var b = endPanel.GetComponentInChildren<Button>();
            if (b != null) EventSystem.current?.SetSelectedGameObject(b.gameObject);
            Cursor.visible = true;
        }

        // ================================================================== update
        void UpdatePanels(float dt)
        {
            toastT += dt;
            float a = toastT < 0.15f ? toastT / 0.15f : (toastT > toastLife - 0.4f ? (toastLife - toastT) / 0.4f : 1f);
            toast.alpha = Mathf.Clamp01(a);
            toast.transform.localScale = Vector3.one * (toastT < 0.15f ? Mathf.Lerp(1.4f, 1f, toastT / 0.15f) : 1f);
            tutorialGroup.alpha = Mathf.MoveTowards(tutorialGroup.alpha, tutorialVisible ? 1f : 0f, dt * 5f);
            dialogueGroup.alpha = Mathf.MoveTowards(dialogueGroup.alpha, DialogueOpen ? 1f : 0f, dt * 6f);
            dialogueHint.alpha = 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 6f);

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
