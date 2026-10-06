using TMPro;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// "TEMPRANO" / "TARDE" sobre la cabeza de Kaito cuando erra un parry por poco. Antes un parry mal
    /// medido solo dolía: no había forma de saber si había que esperar más o apretar antes.
    ///  * TEMPRANO: el golpe llegó apenas después de que se cerró su ventana (o en la guardia imperfecta).
    ///  * TARDE: apretó parry hasta 0.2 s después de recibir un golpe desviable.
    /// Es ayuda de aprendizaje: aparece las primeras <see cref="MaxLabels"/> veces (se cuenta en PlayerPrefs:
    /// es la mano del jugador la que aprende, no la partida). Lienzo propio, no toca la UI.
    /// </summary>
    public class TimingCoach : MonoBehaviour
    {
        public const int MaxLabels = 12;
        const string PrefKey = "nindo.timingCoach";
        const float Life = 0.8f;

        static readonly Color EarlyColor = new Color(0.72f, 0.86f, 1f);
        static readonly Color LateColor = new Color(1f, 0.58f, 0.36f);

        Canvas canvas;
        RectTransform root;
        TextMeshProUGUI label;
        float t = Life;

        /// <summary>Muestra la pista de tiempo (si todavía corresponde).</summary>
        public void Timing(bool early)
        {
            int shown = PlayerPrefs.GetInt(PrefKey, 0);
            if (shown >= MaxLabels) return;
            PlayerPrefs.SetInt(PrefKey, shown + 1);
            Show(early ? "TEMPRANO" : "TARDE", early ? EarlyColor : LateColor);
        }

        void Show(string text, Color c)
        {
            if (canvas == null) Build();
            label.text = text;
            label.color = c;
            t = 0f;
            canvas.enabled = true;
            Place();
        }

        void Build()
        {
            // debajo del lienzo de la UI (orden 10): el menú de pausa y los diálogos lo tapan
            canvas = UIFactory.CreateCanvas("Nindo Coach", 9);
            canvas.transform.SetParent(transform, false);
            root = (RectTransform)canvas.transform;
            label = UIFactory.Text("Timing", root, "", 34, Color.white, Vector2.zero, Vector2.zero, new Vector2(320, 60), TextAlignmentOptions.Center, true);
            label.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            UIFactory.Outline(label, 0.3f);
            canvas.enabled = false;
        }

        void LateUpdate()
        {
            if (canvas == null || !canvas.enabled) return;
            // tiempo real: tiene que poder leerse aunque la pelea esté en cámara lenta o en hit-stop
            t += Time.unscaledDeltaTime;
            if (t >= Life || Game.InCutscene || Game.IsPaused) { canvas.enabled = false; return; }
            Place();
        }

        void Place()
        {
            var p = Game.Player;
            var cam = Game.Camera != null ? Game.Camera.Cam : null;
            if (p == null || cam == null) { canvas.enabled = false; return; }
            Vector3 sp = cam.WorldToScreenPoint(p.transform.position + Vector3.up * 2.3f);
            if (sp.z < 0f) { canvas.enabled = false; return; }
            float scale = root.localScale.x > 0f ? root.localScale.x : 1f;
            float k = t / Life;
            // salta, sube un poco y se desvanece en el último tercio
            float pop = k < 0.12f ? Mathf.Lerp(0.6f, 1.15f, k / 0.12f) : Mathf.Lerp(1.15f, 1f, Mathf.Clamp01((k - 0.12f) / 0.12f));
            label.rectTransform.anchoredPosition = new Vector2(sp.x, sp.y) / scale + new Vector2(0f, 28f * k);
            label.rectTransform.localScale = Vector3.one * pop;
            var c = label.color; c.a = k > 0.66f ? 1f - (k - 0.66f) / 0.34f : 1f; label.color = c;
        }
    }
}
