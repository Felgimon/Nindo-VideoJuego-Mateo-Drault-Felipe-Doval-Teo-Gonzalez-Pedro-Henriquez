using UnityEngine;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// Avisos de golpe que llegan desde fuera de la pantalla: un trazo de pincel en el borde, apuntando al atacante,
    /// con un ensō chico que se va cerrando igual que el anillo del suelo (mismo TellProgress01: cierra en el momento
    /// de apretar). Dorado y una flecha = se desvía (parry); rojo y flecha doble = imparable (dash). La forma también
    /// cambia: no depende solo del color. Sin texto ni símbolos.
    /// Solo lo que ya dibuja su aviso y está fuera del 92 % central o detrás de la cámara; desaparece 0.15 s después
    /// del golpe. Lee únicamente la API pública de Enemy (InTell, TellProgress01, StepKind, StrikeEta, IsAlive).
    /// Se cuelga del canvas del juego por su cuenta (lienzo anidado debajo del HUD), sin tocar UIManager.
    /// </summary>
    [DefaultExecutionOrder(520)]
    public class ThreatIndicators : MonoBehaviour
    {
        const int PoolSize = 4;
        /// <summary>Margen al borde de la pantalla (unidades del canvas de 1920x1080).</summary>
        const float EdgeMargin = 78f;
        const float FadeOut = 0.15f;

        class Mark
        {
            public RectTransform root, arrow;
            public Image ink, stroke, ringInk, ring;
            public CanvasGroup group;
            public Enemy enemy;
            public int tellId;
            public float alpha, lastSeen;
            public bool danger;
        }

        readonly Mark[] marks = new Mark[PoolSize];
        RectTransform layer;
        Canvas rootCanvas;

        void LateUpdate()
        {
            if (layer == null && !Build()) return;
            float dt = Time.unscaledDeltaTime, now = Time.unscaledTime;
            var cam = Game.Camera != null ? Game.Camera.Cam : null;
            var combat = Game.Combat;
            bool show = cam != null && combat != null && Game.Player != null && Game.Player.IsAlive && !Game.InCutscene && !Game.IsPaused;
            if (show)
            {
                var list = combat.Engaged;
                for (int i = 0; i < list.Count; i++) Consider(list[i], cam, now);
                var boss = combat.ActiveBoss;
                if (boss != null && !Contains(list, boss)) Consider(boss, cam, now);
            }
            Vector2 size = layer.rect.size;
            foreach (var m in marks)
            {
                bool live = show && m.enemy != null && now - m.lastSeen < 0.05f;
                m.alpha = Mathf.MoveTowards(m.alpha, live ? 1f : 0f, dt / (live ? 0.08f : FadeOut));
                if (m.alpha <= 0f) { if (m.root.gameObject.activeSelf) m.root.gameObject.SetActive(false); if (!live) m.enemy = null; continue; }
                if (!m.root.gameObject.activeSelf) m.root.gameObject.SetActive(true);
                m.group.alpha = m.alpha;
                if (m.enemy != null && cam != null) Place(m, cam, size, now);
            }
        }

        static bool Contains(System.Collections.Generic.IReadOnlyList<Enemy> list, Enemy e)
        {
            for (int i = 0; i < list.Count; i++) if (list[i] == e) return true;
            return false;
        }

        /// <summary>¿Avisa fuera de cuadro? Le asigna (o mantiene) una marca.</summary>
        void Consider(Enemy e, Camera cam, float now)
        {
            if (e == null || !e.IsAlive || !e.InTell) return;
            Vector3 v = cam.WorldToViewportPoint(e.AimPoint);
            bool offscreen = v.z <= 0f || v.x < 0.04f || v.x > 0.96f || v.y < 0.04f || v.y > 0.96f;
            if (!offscreen) return;
            Mark free = null;
            foreach (var m in marks)
            {
                if (m.enemy == e) { free = m; break; }
                if (free == null && (m.enemy == null || m.alpha <= 0f)) free = m;
            }
            if (free == null) return;
            if (free.enemy != e || free.tellId != e.TellId)
            {
                free.enemy = e;
                free.tellId = e.TellId;
                free.danger = e.StepKind == AttackKind.Unblockable;
                free.stroke.sprite = free.danger ? doubleSprite : singleSprite;
                free.ink.sprite = free.danger ? doubleInkSprite : singleInkSprite;
            }
            free.lastSeen = now;
        }

        void Place(Mark m, Camera cam, Vector2 size, float now)
        {
            var e = m.enemy;
            Vector3 v = cam.WorldToViewportPoint(e.AimPoint);
            // detrás de la cámara la proyección sale espejada: se da vuelta para que apunte hacia donde está
            Vector2 d = new Vector2(v.x - 0.5f, v.y - 0.5f);
            if (v.z < 0f) d = -d;
            if (d.sqrMagnitude < 1e-6f) d = Vector2.down;
            d.x *= size.x; d.y *= size.y;
            // intersección del rayo desde el centro con el rectángulo interior (los bordes, no una elipse: en 16:9
            // la elipse dejaba las marcas laterales demasiado adentro)
            float hx = size.x * 0.5f - EdgeMargin, hy = size.y * 0.5f - EdgeMargin;
            float k = Mathf.Min(hx / Mathf.Max(1e-3f, Mathf.Abs(d.x)), hy / Mathf.Max(1e-3f, Mathf.Abs(d.y)));
            m.root.anchoredPosition = d * k;
            m.arrow.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg);

            float p = e.InTell ? e.TellProgress01 : 1f;
            Color c = m.danger ? TellStyle.Crimson : Color.Lerp(TellStyle.Gold, TellStyle.GoldHot, p);
            m.stroke.color = c;
            m.ring.color = c;
            m.ring.fillAmount = p;
            // late más rápido a medida que se cierra; al cerrarse, un golpe de escala (el momento de apretar)
            float beat = 1f + 0.06f * Mathf.Sin(now * Mathf.Lerp(8f, 22f, p));
            float close = p >= 0.98f ? 1.22f : 1f;
            m.root.localScale = Vector3.one * Mathf.Lerp(m.root.localScale.x, beat * close, 0.5f);
        }

        // ------------------------------------------------------------------ construcción
        bool Build()
        {
            var ui = Game.UI;
            if (ui == null) return false;
            var c = ui.GetComponentInChildren<Canvas>();
            if (c == null) return false;
            rootCanvas = c.rootCanvas;
            var go = new GameObject("Amenazas", typeof(RectTransform));
            layer = (RectTransform)go.transform;
            layer.SetParent(rootCanvas.transform, false);
            layer.anchorMin = Vector2.zero; layer.anchorMax = Vector2.one;
            layer.offsetMin = layer.offsetMax = Vector2.zero;
            // justo encima de las marcas sobre el mundo y debajo del HUD y de los fundidos
            var world = rootCanvas.transform.Find("World");
            layer.SetSiblingIndex(world != null ? world.GetSiblingIndex() + 1 : 0);
            // lienzo anidado: lo que se mueve cada frame se reconstruye solo, sin tocar el resto de la UI
            go.AddComponent<Canvas>();
            MakeSprites();
            for (int i = 0; i < PoolSize; i++) marks[i] = MakeMark(i);
            return true;
        }

        Mark MakeMark(int i)
        {
            var m = new Mark();
            var root = new GameObject("Amenaza" + i, typeof(RectTransform), typeof(CanvasGroup));
            m.root = (RectTransform)root.transform;
            m.root.SetParent(layer, false);
            m.root.sizeDelta = new Vector2(120f, 120f);
            m.group = root.GetComponent<CanvasGroup>();
            m.group.interactable = false; m.group.blocksRaycasts = false;
            // ensō chico (tinta debajo para que se lea sobre la nieve o el lago)
            m.ringInk = Img("TintaAnillo", m.root, ringSprite, new Color(TellStyle.Ink.r, TellStyle.Ink.g, TellStyle.Ink.b, 0.55f), 76f);
            m.ringInk.rectTransform.localScale = Vector3.one * 1.12f;
            m.ring = Img("Anillo", m.root, ringSprite, TellStyle.Gold, 76f);
            m.ring.type = Image.Type.Filled; m.ring.fillMethod = Image.FillMethod.Radial360;
            m.ring.fillOrigin = (int)Image.Origin360.Top; m.ring.fillClockwise = true;
            // la flecha gira alrededor del centro y queda del lado de afuera del anillo
            var arrow = new GameObject("Flecha", typeof(RectTransform));
            m.arrow = (RectTransform)arrow.transform;
            m.arrow.SetParent(m.root, false);
            m.ink = Img("Tinta", m.arrow, singleInkSprite, new Color(TellStyle.Ink.r, TellStyle.Ink.g, TellStyle.Ink.b, 0.7f), 64f);
            m.stroke = Img("Trazo", m.arrow, singleSprite, TellStyle.Gold, 64f);
            m.ink.rectTransform.anchoredPosition = m.stroke.rectTransform.anchoredPosition = new Vector2(52f, 0f);
            root.SetActive(false);
            return m;
        }

        static Image Img(string name, Transform parent, Sprite s, Color c, float size)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image));
            var img = go.GetComponent<Image>();
            img.rectTransform.SetParent(parent, false);
            img.rectTransform.sizeDelta = new Vector2(size, size);
            img.sprite = s; img.color = c; img.raycastTarget = false;
            return img;
        }

        // ------------------------------------------------------------------ pinceladas procedurales
        static Sprite singleSprite, doubleSprite, singleInkSprite, doubleInkSprite, ringSprite;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() { singleSprite = doubleSprite = singleInkSprite = doubleInkSprite = ringSprite = null; }

        static void MakeSprites()
        {
            if (singleSprite != null) return;
            singleSprite = Sprite.Create(Chevron(false, 0f), new Rect(0, 0, Tex, Tex), new Vector2(0.5f, 0.5f));
            doubleSprite = Sprite.Create(Chevron(true, 0f), new Rect(0, 0, Tex, Tex), new Vector2(0.5f, 0.5f));
            singleInkSprite = Sprite.Create(Chevron(false, 0.05f), new Rect(0, 0, Tex, Tex), new Vector2(0.5f, 0.5f));
            doubleInkSprite = Sprite.Create(Chevron(true, 0.05f), new Rect(0, 0, Tex, Tex), new Vector2(0.5f, 0.5f));
            ringSprite = Sprite.Create(Enso(), new Rect(0, 0, Tex, Tex), new Vector2(0.5f, 0.5f));
        }

        const int Tex = 128;

        /// <summary>
        /// Flecha de pincel apuntando a +x: dos trazos que se juntan en la punta, gruesos donde apoya el pincel y
        /// afinándose hacia la cola, con estrías de pincel seco a lo largo del trazo. 'grow' engorda la forma para la
        /// tinta de abajo.
        /// </summary>
        static Texture2D Chevron(bool twin, float grow)
        {
            var px = new Color32[Tex * Tex];
            for (int y = 0; y < Tex; y++)
                for (int x = 0; x < Tex; x++)
                {
                    Vector2 p = new Vector2((x + 0.5f) / Tex, (y + 0.5f) / Tex);
                    float a = Stroke(p, 0f, grow);
                    if (twin) a = Mathf.Max(a, Stroke(p, -0.24f, grow));
                    px[y * Tex + x] = new Color32(255, 255, 255, (byte)(Mathf.Clamp01(a) * 255f));
                }
            return Upload(px);
        }

        static float Stroke(Vector2 p, float shift, float grow)
        {
            // escala: la doble flecha entra en el mismo cuadro
            Vector2 tip = new Vector2(0.84f + shift, 0.5f);
            float a = 0f;
            for (int s = -1; s <= 1; s += 2)
            {
                Vector2 tail = new Vector2(0.36f + shift, 0.5f + s * 0.34f);
                Vector2 ab = tip - tail;
                float t = Mathf.Clamp01(Vector2.Dot(p - tail, ab) / ab.sqrMagnitude);
                float dist = (p - (tail + ab * t)).magnitude;
                // grosor: fino en la cola, apoyo del pincel en la punta
                float w = Mathf.Lerp(0.025f, 0.075f, t * t) + grow;
                float edge = 1f - Mathf.SmoothStep(w * 0.75f, w, dist);
                // pincel seco: estrías paralelas al trazo que se abren hacia la cola
                float across = Vector2.Dot(p - tail, new Vector2(-ab.y, ab.x).normalized);
                float streak = Mathf.PerlinNoise(across * 90f + s * 13.1f, t * 3f + shift * 7f);
                float dry = grow > 0f ? 1f : Mathf.Lerp(1f, Mathf.SmoothStep(0.25f, 0.55f, streak), (1f - t) * 0.85f);
                a = Mathf.Max(a, edge * dry);
            }
            return a;
        }

        /// <summary>Ensō: anillo de pincel que arranca grueso arriba y se afina dando la vuelta.</summary>
        static Texture2D Enso()
        {
            var px = new Color32[Tex * Tex];
            for (int y = 0; y < Tex; y++)
                for (int x = 0; x < Tex; x++)
                {
                    Vector2 p = new Vector2((x + 0.5f) / Tex - 0.5f, (y + 0.5f) / Tex - 0.5f);
                    float r = p.magnitude;
                    // ángulo desde arriba en sentido horario (igual que el relleno Radial360 desde Top)
                    float ang = Mathf.Repeat(Mathf.Atan2(p.x, p.y) / (2f * Mathf.PI), 1f);
                    float w = Mathf.Lerp(0.07f, 0.035f, ang);
                    float d = Mathf.Abs(r - 0.38f);
                    float a = 1f - Mathf.SmoothStep(w * 0.7f, w, d);
                    a *= Mathf.Lerp(1f, Mathf.SmoothStep(0.2f, 0.5f, Mathf.PerlinNoise(ang * 40f, r * 60f)), ang * 0.7f);
                    px[y * Tex + x] = new Color32(255, 255, 255, (byte)(Mathf.Clamp01(a) * 255f));
                }
            return Upload(px);
        }

        static Texture2D Upload(Color32[] px)
        {
            var t = new Texture2D(Tex, Tex, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear };
            t.SetPixels32(px);
            t.Apply(true, true);
            return t;
        }
    }
}
