using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// Menú principal (escena "Menu"). Conserva la idea del equipo: la máscara con los ojos
    /// cerrados que se abren al empezar a jugar. Todo se construye por código.
    /// </summary>
    public class MenuBootstrap : MonoBehaviour
    {
        Image eyesClosed, eyesOpen;
        CanvasGroup buttons, title;
        bool starting;

        IEnumerator Start()
        {
            Cursor.visible = true;
            Cursor.lockState = CursorLockMode.None;
            Time.timeScale = 1f;
            var content = Game.LoadContent();
            new GameObject("[Systems]").AddComponent<InputReader>();
            AudioManager.Ensure();
            var ui = new GameObject("[UI]").AddComponent<UIManager>();
            ui.SetFade(1f);
            if (Camera.main == null)
            {
                var cam = new GameObject("Main Camera").AddComponent<Camera>();
                cam.tag = "MainCamera";
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.03f, 0.03f, 0.06f);
                cam.gameObject.AddComponent<AudioListener>();
            }

            var canvas = UIFactory.CreateCanvas("Menu", 5);
            var root = (RectTransform)canvas.transform;
            var bg = UIFactory.Image("Bg", root, new Color(0.03f, 0.03f, 0.06f, 1f));
            bg.rectTransform.Fill(Vector2.zero, Vector2.zero);
            eyesClosed = UIFactory.Image("EyesClosed", root, Color.white, content.menuEyesClosed);
            eyesClosed.preserveAspect = true;
            eyesClosed.rectTransform.Fill(new Vector2(0, 0), new Vector2(0, 0));
            eyesOpen = UIFactory.Image("EyesOpen", root, new Color(1, 1, 1, 0), content.menuEyesOpen);
            eyesOpen.preserveAspect = true;
            eyesOpen.rectTransform.Fill(new Vector2(0, 0), new Vector2(0, 0));
            if (content.menuEyesClosed == null) eyesClosed.color = new Color(0, 0, 0, 0);

            // luciérnagas de UI flotando
            for (int i = 0; i < 26; i++)
            {
                var f = UIFactory.Image("Firefly", root, new Color(0.9f, 1f, 0.5f, 0.6f), new Vector2(Random.value, Random.value), Vector2.zero, Vector2.one * Random.Range(4f, 9f), FXMaterials.SoftDot != null ? Sprite.Create(FXMaterials.SoftDot, new Rect(0, 0, 64, 64), Vector2.one * 0.5f) : null);
                f.gameObject.AddComponent<UIFirefly>();
            }

            var titleRt = UIFactory.Rect("Title", root, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0, -40), new Vector2(1200, 220));
            title = titleRt.gameObject.AddComponent<CanvasGroup>();
            var t1 = UIFactory.Text("Kanji", titleRt, "忍道", 120, UIFactory.Gold, new Vector2(0.5f, 1f), new Vector2(0, 0), new Vector2(600, 140), TextAlignmentOptions.Center, true);
            UIFactory.Outline(t1, 0.2f);
            var t2 = UIFactory.Text("Name", titleRt, "N I N D Ō", 54, UIFactory.Paper, new Vector2(0.5f, 1f), new Vector2(0, -140), new Vector2(800, 70), TextAlignmentOptions.Center, true);
            UIFactory.Outline(t2, 0.2f);

            var brt = UIFactory.Rect("Buttons", root, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0, 80), new Vector2(600, 420));
            buttons = brt.gameObject.AddComponent<CanvasGroup>();
            float y = 340;
            Button first = null;
            if (SaveSystem.HasSave)
            {
                var c = UIFactory.Button("Continue", brt, "Continuar", new Vector2(480, 74), () => Play(false));
                c.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, y - 200); y -= 92; first = c;
            }
            var n = UIFactory.Button("New", brt, "Nueva partida", new Vector2(480, 74), () => Play(true));
            n.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, y - 200); y -= 92; if (first == null) first = n;
            var o = UIFactory.Button("Options", brt, "Opciones", new Vector2(480, 74), () => Game.UI.OpenOptions(false));
            o.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, y - 200); y -= 92;
            var q = UIFactory.Button("Quit", brt, "Salir", new Vector2(480, 74), Application.Quit);
            q.GetComponent<RectTransform>().anchoredPosition = new Vector2(0, y - 200);
            ui.transform.SetAsLastSibling();
            EventSystem.current?.SetSelectedGameObject(first.gameObject);

            Game.Audio.PlayMusic("menu", 2f);
            Game.Audio.PlayAmbience("night");
            yield return ui.Fade(0f, 1.5f);
        }

        void Play(bool newGame)
        {
            if (starting) return;
            starting = true;
            buttons.interactable = false;
            StartCoroutine(OpenEyes(newGame));
        }

        IEnumerator OpenEyes(bool newGame)
        {
            Game.Audio?.Play("ui_start", null, 0.8f);
            float t = 0f;
            while (t < 1.6f)
            {
                t += Time.unscaledDeltaTime;
                float k = t / 1.6f;
                buttons.alpha = 1f - k * 3f;
                eyesOpen.color = new Color(1, 1, 1, k);
                if (eyesClosed.sprite != null) eyesClosed.color = new Color(1, 1, 1, 1f - k);
                yield return null;
            }
            yield return new WaitForSecondsRealtime(0.6f);
            Game.Audio?.StopMusic(1.5f);
            SceneFlow.StartGame(newGame);
        }
    }

    public class UIFirefly : MonoBehaviour
    {
        RectTransform rt; Vector2 basePos; float seed; Image img;
        void Start() { rt = (RectTransform)transform; basePos = rt.anchoredPosition; seed = Random.value * 100f; img = GetComponent<Image>(); }
        void Update()
        {
            float t = Time.unscaledTime * 0.3f + seed;
            rt.anchoredPosition = basePos + new Vector2(Mathf.PerlinNoise(t, 0.1f) - 0.5f, Mathf.PerlinNoise(0.2f, t) - 0.5f) * 140f;
            var c = img.color; c.a = 0.2f + 0.6f * Mathf.PerlinNoise(t * 3f, seed); img.color = c;
        }
    }
}
