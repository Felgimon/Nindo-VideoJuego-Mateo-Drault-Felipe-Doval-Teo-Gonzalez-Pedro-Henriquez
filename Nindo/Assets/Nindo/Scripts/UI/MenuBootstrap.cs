using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// Menú principal (escena "Menu"). Conserva la idea del equipo: la máscara con los ojos
    /// cerrados que se abren al empezar a jugar, con su logo de pincel sobre la bandana y los ítems con la
    /// cinta roja (NindoMenuItem). Todo se construye por código.
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
            // Expand: el recuadro 16:9 del arte mide siempre 1920x1080 unidades, así el título y los
            // botones (de tamaño fijo) quedan sobre la bandana y debajo de la máscara en 4:3, 21:9, 32:9...
            canvas.GetComponent<CanvasScaler>().screenMatchMode = CanvasScaler.ScreenMatchMode.Expand;
            var root = (RectTransform)canvas.transform;
            var bg = UIFactory.Image("Bg", root, new Color(0.03f, 0.03f, 0.06f, 1f));
            bg.rectTransform.Fill(Vector2.zero, Vector2.zero);
            // el arte del equipo es 16:9: lo que se apoya en él (título sobre la bandana, botones bajo la
            // máscara) va en un contenedor con la misma proporción, así queda alineado en cualquier pantalla
            var art = UIFactory.Rect("Art", root, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(1920, 1080));
            var fit = art.gameObject.AddComponent<AspectRatioFitter>();
            fit.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
            fit.aspectRatio = 16f / 9f;
            eyesClosed = UIFactory.Image("EyesClosed", art, Color.white, content.menuEyesClosed);
            eyesClosed.preserveAspect = true;
            eyesClosed.rectTransform.Fill(new Vector2(0, 0), new Vector2(0, 0));
            eyesOpen = UIFactory.Image("EyesOpen", art, new Color(1, 1, 1, 0), content.menuEyesOpen);
            eyesOpen.preserveAspect = true;
            eyesOpen.rectTransform.Fill(new Vector2(0, 0), new Vector2(0, 0));
            if (content.menuEyesClosed == null) eyesClosed.color = new Color(0, 0, 0, 0);

            // luciérnagas de UI flotando
            for (int i = 0; i < 26; i++)
            {
                var f = UIFactory.Image("Firefly", root, new Color(0.9f, 1f, 0.5f, 0.6f), new Vector2(Random.value, Random.value), Vector2.zero, Vector2.one * Random.Range(4f, 9f), UISprites.SoftDot);
                f.gameObject.AddComponent<UIFirefly>();
            }

            // el logo de pincel del equipo, en tinta sobre la bandana amarilla (como un hachimaki). Antes el nombre
            // iba en texto Mincho y el logo (Sprites/Logo.jpg) no se usaba en ningún lado
            var ink = content.menuEyesClosed != null ? new Color(0.1f, 0.06f, 0.05f, 0.95f) : UIFactory.Gold;
            var titleRt = UIFactory.Rect("Title", art, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0, -36), new Vector2(1200, 290));
            title = titleRt.gameObject.AddComponent<CanvasGroup>();
            if (content.logo != null)
            {
                var logo = UIFactory.Image("Logo", titleRt, ink, new Vector2(0.5f, 1f), Vector2.zero, new Vector2(230f * content.logo.rect.width / content.logo.rect.height, 230f), content.logo);
                logo.preserveAspect = true;
            }
            else UIFactory.Text("Name", titleRt, "NINDŌ", 132, ink, new Vector2(0.5f, 1f), new Vector2(0, -20), new Vector2(900, 160), TextAlignmentOptions.Center, true);
            UIFactory.Text("Motto", titleRt, "El camino ninja", 32, ink, new Vector2(0.5f, 1f), new Vector2(0, -232), new Vector2(800, 46), TextAlignmentOptions.Center, true);

            // ítems en fila, debajo de la máscara (antes tapaban los ojos, que son la gracia del menú)
            var brt = UIFactory.Rect("Buttons", art, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0, 34), new Vector2(1600, 90));
            buttons = brt.gameObject.AddComponent<CanvasGroup>();
            var list = new System.Collections.Generic.List<Button>();
            var size = new Vector2(300, 74);
            if (SaveSystem.HasSave) list.Add(UIFactory.MenuItem("Continue", brt, "Continuar", size, () => Play(false), 38f, TextAlignmentOptions.Center));
            list.Add(UIFactory.MenuItem("New", brt, "Nueva partida", size, () => Play(true), 38f, TextAlignmentOptions.Center));
            list.Add(UIFactory.MenuItem("Options", brt, "Opciones", size, () => Game.UI.OpenOptions(false, buttons), 38f, TextAlignmentOptions.Center));
            list.Add(UIFactory.MenuItem("Quit", brt, "Salir", size, Application.Quit, 38f, TextAlignmentOptions.Center));
            const float w = 300f, gap = 70f;
            float x0 = -(list.Count * w + (list.Count - 1) * gap) * 0.5f + w * 0.5f;
            for (int i = 0; i < list.Count; i++) list[i].GetComponent<RectTransform>().anchoredPosition = new Vector2(x0 + i * (w + gap), 45f);
            Button first = list[0];
            ui.transform.SetAsLastSibling();
            var item = first.GetComponent<NindoMenuItem>();
            if (item != null) item.silent = true;
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
