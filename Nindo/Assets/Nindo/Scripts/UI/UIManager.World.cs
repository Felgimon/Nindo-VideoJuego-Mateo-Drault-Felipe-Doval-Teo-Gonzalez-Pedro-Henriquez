using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// Lo que se dibuja sobre el mundo: la barrita de cada enemigo con su postura, el kunai del fijado, el aviso
    /// de remate, el de interactuar, las marcas de combate y los avisos de Kaito ("¡FILO DE IRA!", "¡Parry!").
    /// Regla: nada tapa el cuerpo de un enemigo que pelea (el aviso del golpe se lee en su cuerpo y en el anillo
    /// del piso): todo va ARRIBA de la barra, y las barras de enemigos juntos se apilan en vez de pisarse.
    /// </summary>
    public partial class UIManager
    {
        class EnemyWidget
        {
            public RectTransform rt;
            public Image back, glow, fill, ghost, guard;
            public Image[] pips;
            public TextMeshProUGUI status;
            public Enemy enemy;
            public float visibleUntil, ghostValue = 1f, ghostHold, lastHp = -1f;
            public string statusText = "";
            public bool wasOpen, tipText, shown, snap;
            public Vector2 head, pos;            // cabeza proyectada y dónde se dibuja (con lo apilado, suavizado)
            public float height, target, stack;  // alto ocupado; altura apilada a la que va y corrimiento actual
            public int rank;                     // orden de abajo arriba del cuadro anterior
        }
        readonly List<EnemyWidget> widgets = new List<EnemyWidget>();
        readonly Dictionary<Enemy, EnemyWidget> widgetOf = new Dictionary<Enemy, EnemyWidget>();
        EnemyWidget[] sortBuf = new EnemyWidget[16];

        RectTransform lockChevron;
        Image lockImg;
        Enemy lockTarget;
        float lockPopT = 1f;

        RectTransform finisherRoot, finisherKey;
        Image finisherRibbon, finisherIcon;
        TextMeshProUGUI finisherLabel;
        Enemy finisherShown;
        float finisherT;
        int finisherAfford = -1;

        RectTransform interactRoot, interactKey;
        Image interactSwash;
        TextMeshProUGUI interactLabel;
        Interactable interactTarget, interactShown;
        string interactText;
        float interactT;

        class Marker { public RectTransform rt; public Image img; public Enemy e; public float t, life, size; public int kind; public bool active; }
        readonly List<Marker> markers = new List<Marker>();
        const int MarkAlert = 0, MarkUnblockable = 1, MarkGuard = 2;

        class Callout { public RectTransform rt; public TextMeshProUGUI text; public float t, life, lift; public bool active; }
        readonly Callout[] callouts = new Callout[3];

        static readonly Color EnemyRed = new Color(0.89f, 0.16f, 0.12f), PipOff = new Color(0.33f, 0.31f, 0.35f, 0.9f);

        void BuildWorldMarkers()
        {
            // kunai dorado que apunta para abajo, ARRIBA de la barra del fijado. Antes era un rombo que giraba sobre
            // el torso y tapaba entre la mitad y tres cuartos del ninja: justo donde se lee la anticipación del golpe
            var chev = UIFactory.Centered("Lock", world, UIFactory.Gold, Vector2.zero, Vector2.zero, new Vector2(76, 27), UISprites.Kunai);
            lockChevron = chev.rectTransform;
            lockChevron.localRotation = Quaternion.Euler(0, 0, -90f);
            lockImg = chev;
            chev.enabled = false;

            // remate: la tecla, el ícono y "Ejecutar" sobre una pincelada de tinta, como el aviso de interactuar (antes
            // una cinta roja: se confundía con la bandana de la vida). Lo distinguen el oro del texto y el ícono
            finisherRoot = UIFactory.Rect("Finisher", world, Vector2.zero, Vector2.zero, new Vector2(0.5f, 0f), Vector2.zero, new Vector2(300, 60));
            finisherRibbon = UIFactory.Image("Swash", finisherRoot, new Color(0.043f, 0.039f, 0.051f, 0.8f), UISprites.BrushSwash);
            finisherRibbon.rectTransform.Fill(new Vector2(-30f, -8f), new Vector2(30f, 8f));
            finisherKey = UIFactory.KeyCap(finisherRoot, "F", 44f, new Vector2(0f, 0.5f), new Vector2(42f, 1f));
            finisherIcon = UIFactory.Centered("Icon", finisherRoot, UIFactory.Gold, new Vector2(0f, 0.5f), new Vector2(90f, 0f), new Vector2(36, 36), UISprites.Finisher);
            finisherLabel = UIFactory.NoWrap(UIFactory.Text("Label", finisherRoot, "Ejecutar", 30, UIFactory.Gold, new Vector2(0f, 0.5f), new Vector2(112f, 0f), new Vector2(200, 50), TextAlignmentOptions.Left, true));
            finisherLabel.rectTransform.pivot = new Vector2(0f, 0.5f);
            UIFactory.Outline(finisherLabel, 0.2f);
            finisherRoot.gameObject.SetActive(false);

            // interactuar: tecla + texto sobre un trazo de tinta
            interactRoot = UIFactory.Rect("Interact", world, Vector2.zero, Vector2.zero, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(300, 64));
            interactSwash = UIFactory.Image("Swash", interactRoot, new Color(0.043f, 0.039f, 0.051f, 0.75f), UISprites.BrushSwash);
            interactSwash.rectTransform.Fill(new Vector2(-30f, -8f), new Vector2(30f, 8f));
            interactKey = UIFactory.KeyCap(interactRoot, "E", 40f, new Vector2(0f, 0.5f), new Vector2(26f, 1f));
            interactLabel = UIFactory.NoWrap(UIFactory.Text("Label", interactRoot, "", 28, UIFactory.Paper, new Vector2(0f, 0.5f), new Vector2(54f, 0f), new Vector2(400, 44), TextAlignmentOptions.Left));
            interactLabel.rectTransform.pivot = new Vector2(0f, 0.5f);
            UIFactory.Outline(interactLabel, 0.18f);
            interactRoot.gameObject.SetActive(false);

            for (int i = 0; i < callouts.Length; i++)
            {
                var t = UIFactory.NoWrap(UIFactory.Text("Callout", world, "", 38, UIFactory.Gold, Vector2.zero, Vector2.zero, new Vector2(620, 56), TextAlignmentOptions.Bottom, true));
                t.rectTransform.pivot = new Vector2(0.5f, 0f);
                UIFactory.Outline(t, 0.3f);
                t.enabled = false;
                callouts[i] = new Callout { rt = t.rectTransform, text = t };
            }
        }

        EnemyWidget GetWidget(Enemy e)
        {
            if (widgetOf.TryGetValue(e, out var w)) return w;
            w = null;
            foreach (var x in widgets) if (x.enemy == null || !x.enemy.IsAlive || !x.enemy.gameObject.activeInHierarchy) { w = x; break; }
            if (w == null)
            {
                w = new EnemyWidget();
                w.rt = UIFactory.Rect("EnemyBar", world, Vector2.zero, Vector2.zero, new Vector2(0.5f, 0f), Vector2.zero, new Vector2(124, 64));
                // trazo de tinta con la vida en carmesí y una estela de papel (lo que se perdió). 20 de alto: con 16 la
                // banda roja (el relleno es opaco en 47 de sus 72 filas) quedaba en 6 px a 1080p y 4 a 720p, y es lo
                // que se lee de cada ninja en una pelea grupal
                w.glow = UIFactory.Sliced("Glow", w.rt, UISprites.BossBarBack, new Color(1f, 0.8f, 0.35f, 0f), 30f);
                Place(w.glow.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, -6f), new Vector2(128, 30));
                w.glow.rectTransform.pivot = new Vector2(0.5f, 0f);
                w.back = UIFactory.Sliced("Back", w.rt, UISprites.BossBarBack, Color.white, 20f);
                Place(w.back.rectTransform, new Vector2(0.5f, 0f), Vector2.zero, new Vector2(116, 20));
                w.back.rectTransform.pivot = new Vector2(0.5f, 0f);
                w.ghost = WidgetFill("Ghost", w.back.rectTransform, new Color(UIFactory.Paper.r, UIFactory.Paper.g, UIFactory.Paper.b, 0.8f));
                w.fill = WidgetFill("Hp", w.back.rectTransform, EnemyRed);
                w.pips = new Image[6];
                for (int i = 0; i < w.pips.Length; i++)
                    w.pips[i] = UIFactory.Centered("Pip" + i, w.rt, PipOff, new Vector2(0.5f, 0f), new Vector2((i - 2.5f) * 17f, PipY), new Vector2(15, 15), UISprites.Pip);
                w.guard = UIFactory.Centered("Guard", w.rt, UIFactory.Steel, new Vector2(0.5f, 0f), new Vector2(72f, 10f), new Vector2(24, 24), UISprites.Guard);
                w.guard.enabled = false;
                w.status = UIFactory.NoWrap(UIFactory.Text("Status", w.rt, "", 24, UIFactory.Gold, new Vector2(0.5f, 0f), new Vector2(0, 42), new Vector2(320, 34), TextAlignmentOptions.Bottom, true));
                w.status.rectTransform.pivot = new Vector2(0.5f, 0f);
                UIFactory.Outline(w.status, 0.25f);
                widgets.Add(w);
            }
            if (w.enemy != null) widgetOf.Remove(w.enemy);
            w.enemy = e;
            w.lastHp = -1f; w.wasOpen = false; w.statusText = ""; w.status.text = "";
            widgetOf[e] = w;
            return w;
        }

        Image WidgetFill(string name, RectTransform back, Color c)
        {
            var img = UIFactory.Image(name, back, c, UISprites.BossBarFill != null ? UISprites.BossBarFill : UIFactory.White);
            img.type = Image.Type.Filled; img.fillMethod = Image.FillMethod.Horizontal;
            img.rectTransform.anchorMin = Vector2.zero; img.rectTransform.anchorMax = Vector2.one;
            img.rectTransform.offsetMin = new Vector2(5f, 2.5f); img.rectTransform.offsetMax = new Vector2(-5f, -2.5f);
            return img;
        }

        const float PipY = 30f;   // centro de los rombos de postura, justo arriba de la barra

        // proyección al canvas del mundo (el canvas está estirado: ancla abajo a la izquierda, en unidades del canvas)
        static bool Project(Camera cam, Vector3 worldPos, float scale, out Vector2 p)
        {
            Vector3 sp = cam.WorldToScreenPoint(worldPos);
            p = new Vector2(sp.x, sp.y) / scale;
            return sp.z > 0f;
        }

        static Vector3 HeadPoint(Enemy e) => e.transform.position + Vector3.up * (e.config.height * e.config.scale + 0.35f);

#if UNITY_EDITOR || DEVELOPMENT_BUILD
        static bool Automated => AutoPilot.Bot || AutoPilot.Busy;
#else
        const bool Automated = false;
#endif

        // la llama WorldMarkersLate, después de que la cámara fija su pose
        internal void UpdateWorldMarkers(float dt)
        {
            var cam = Game.Camera != null ? Game.Camera.Cam : null;
            var p = Game.Player;
            bool show = cam != null && p != null && !HideHud;
            if (world.gameObject.activeSelf != show) world.gameObject.SetActive(show);
            if (!show)
            {
                // las marcas y los avisos son del momento: después de una cinemática, un diálogo o la muerte no
                // vuelven a saltar con el tiempo que les quedaba ("¡FILO DE IRA!" tras la muerte de un jefe). En
                // pausa sí esperan: el juego también está quieto
                if (!PauseOpen) ClearWorldCues();
                return;
            }
            float scale = root.localScale.x > 0 ? root.localScale.x : 1f;
            float t = Time.unscaledTime;

            // ---------------------------------------------------------------- barras de enemigos en combate
            var engaged = Game.Combat != null ? Game.Combat.Engaged : null;
            if (engaged != null)
                for (int i = 0; i < engaged.Count; i++) { var e = engaged[i]; if (e != null && !(e is Boss)) GetWidget(e).visibleUntil = Time.time + 1.5f; }
            int n = 0;
            foreach (var w in widgets)
            {
                var e = w.enemy;
                bool vis = e != null && e.IsAlive && e.gameObject.activeInHierarchy && (Time.time < w.visibleUntil || Time.time - e.LastHitTime < 3f) && !(e is Boss);
                if (vis) vis = Project(cam, HeadPoint(e), scale, out w.head);
                // la que aparece entra directo a su lugar (sin deslizarse desde la cabeza) y va arriba de las demás
                if (vis && !w.shown) { w.snap = true; w.rank = int.MaxValue; }
                if (w.shown != vis) { w.rt.gameObject.SetActive(vis); w.shown = vis; }
                if (!vis) continue;
                UpdateWidget(w, e, dt, t);
                if (n == sortBuf.Length) System.Array.Resize(ref sortBuf, n * 2);
                sortBuf[n++] = w;
            }
            Declutter(n, dt);
            for (int i = 0; i < n; i++) sortBuf[i].rt.anchoredPosition = sortBuf[i].pos;

            // ---------------------------------------------------------------- remate (antes del fijado: el kunai va arriba)
            var cand = p.FinisherCandidate();
            float finisherTop = 0f;
            if (cand != null && p.State != PlayerState.Finisher && Project(cam, HeadPoint(cand), scale, out var fp))
            {
                if (cand != finisherShown) { finisherShown = cand; finisherT = 0f; finisherRoot.gameObject.SetActive(true); }
                finisherT += dt;
                Vector2 basePos = StackTop(cand, fp) + new Vector2(0f, 8f);
                finisherRoot.anchoredPosition = basePos;
                int afford = p.Spirit >= p.config.finisherCost ? 1 : 0;
                if (afford != finisherAfford)
                {
                    finisherAfford = afford;
                    // sin Espíritu el texto se apaga y dice qué falta (el dragón raya cuánto: DenySpirit(costo))
                    finisherLabel.color = afford == 1 ? UIFactory.Gold : new Color(0.62f, 0.59f, 0.56f);
                    finisherLabel.text = afford == 1 ? "Ejecutar" : "Falta Espíritu";
                    finisherLabel.fontSize = afford == 1 ? 30 : 26;
                    finisherIcon.enabled = afford == 1;
                    finisherLabel.rectTransform.anchoredPosition = new Vector2(afford == 1 ? 112f : 74f, 0f);
                }
                if (Game.Input != null) UIFactory.SetKeyCap(finisherKey, Game.Input.Glyph(Act.Finisher));
                // salta al aparecer y después respira suave (antes latía a 9 Hz y nunca quedaba quieto)
                float s = finisherT < 0.12f ? UIAnim.Pop(finisherT, 0.12f) : 1f + 0.025f * Mathf.Sin((finisherT - 0.12f) * Mathf.PI * 2f);
                finisherRoot.localScale = Vector3.one * s;
                finisherTop = basePos.y + 60f;
            }
            else if (finisherShown != null || finisherRoot.gameObject.activeSelf) { finisherShown = null; finisherRoot.gameObject.SetActive(false); }

            UpdateMarkers(cam, scale, dt, t);

            // ---------------------------------------------------------------- fijado (arriba de todo lo de su enemigo)
            if (lockTarget != null && lockTarget.IsAlive && Project(cam, HeadPoint(lockTarget), scale, out var lp))
            {
                lockPopT += dt;
                float top = cand == lockTarget && finisherShown != null ? finisherTop : StackTop(lockTarget, lp).y;
                top = Mathf.Max(top, lockMarkerTop);
                lockChevron.anchoredPosition = new Vector2(lp.x, top + 40f + 4f * Mathf.Sin(t * Mathf.PI * 4f));
                lockChevron.localScale = Vector3.one * UIAnim.Pop(lockPopT, 0.15f, 0.6f, 1.1f);
                lockImg.enabled = true;
            }
            else lockImg.enabled = false;

            // ---------------------------------------------------------------- interactuar
            if (interactTarget != null && interactTarget.isActiveAndEnabled && p.State == PlayerState.Locomotion && Project(cam, interactTarget.PromptPosition, scale, out var ip))
            {
                if (interactTarget != interactShown || interactText != interactTarget.prompt)
                {
                    interactShown = interactTarget; interactText = interactTarget.prompt; interactT = 0f;
                    interactLabel.text = interactText;
                    interactRoot.gameObject.SetActive(true);
                }
                if (Game.Input != null) UIFactory.SetKeyCap(interactKey, Game.Input.Glyph(Act.Interact));
                float kw = interactKey.sizeDelta.x;
                interactKey.anchoredPosition = new Vector2(kw * 0.5f + 6f, 1f);
                interactLabel.rectTransform.anchoredPosition = new Vector2(kw + 18f, 0f);
                interactRoot.sizeDelta = new Vector2(kw + 30f + interactLabel.preferredWidth, 64f);
                interactT += dt;
                interactRoot.anchoredPosition = ip;
                interactRoot.localScale = Vector3.one * UIAnim.Pop(interactT, 0.12f);
            }
            else if (interactShown != null) { interactShown = null; interactRoot.gameObject.SetActive(false); }

            UpdateCallouts(cam, scale, p, dt);
        }

        void UpdateWidget(EnemyWidget w, Enemy e, float dt, float t)
        {
            float hp = e.Health01;
            if (w.lastHp < 0f) { w.lastHp = hp; w.ghostValue = hp; }
            if (hp < w.lastHp - 0.001f) { w.ghostValue = Mathf.Max(w.ghostValue, w.lastHp); w.ghostHold = 0.35f; }
            w.lastHp = hp;
            w.ghostHold -= dt;
            if (w.ghostHold <= 0f) w.ghostValue = Mathf.MoveTowards(w.ghostValue, hp, dt * 0.6f);
            if (w.ghostValue < hp) w.ghostValue = hp;
            w.fill.fillAmount = hp;
            w.ghost.fillAmount = w.ghostValue;

            bool broken = e.PostureBroken, open = e.IsExhausted;
            int max = Mathf.Min(e.config.maxImbalance, w.pips.Length);
            for (int i = 0; i < w.pips.Length; i++)
            {
                bool on = i < max;
                if (w.pips[i].enabled != on) w.pips[i].enabled = on;
                if (!on) continue;
                w.pips[i].rectTransform.anchoredPosition = new Vector2((i - (max - 1) * 0.5f) * 17f, PipY);
                // las fracciones también se ven (parry perfecto +0.5, guardia imperfecta, rebote en la guardia)
                float f = Mathf.Clamp01(e.Imbalance - i);
                w.pips[i].color = open ? Color.Lerp(UIFactory.Gold, Color.white, 0.5f + 0.5f * Mathf.Sin(t * 16f))
                    : f >= 0.99f ? UIFactory.Gold : Color.Lerp(PipOff, UIFactory.Gold, f * 0.6f);
            }
            var gc = w.glow.color;
            gc.a = open ? 0.55f + 0.35f * Mathf.Sin(t * 8f) : 0f;
            w.glow.color = gc;
            bool guarding = e.State == EnemyState.Guard;
            if (w.guard.enabled != guarding) w.guard.enabled = guarding;

            // agotado: la postura quebrada se puede ejecutar ("¡DESEQUILIBRADO!"); sin quebrar es la ventana de daño
            // ("¡ABIERTO!"). El texto sale las primeras veces; después alcanza con los rombos que titilan y el trazo
            // dorado (y con la cinta de "Ejecutar"). Se cuenta en PlayerPrefs: lo aprende la mano, no la partida
            if (open && !w.wasOpen)
            {
                string key = broken ? "nindo.ui.tipBroken" : "nindo.ui.tipOpen";
                int seen = PlayerPrefs.GetInt(key, 0);
                w.tipText = seen < 3;
                if (w.tipText && !Automated) PlayerPrefs.SetInt(key, seen + 1);
            }
            w.wasOpen = open;
            string status = open && w.tipText ? (broken ? "¡DESEQUILIBRADO!" : "¡ABIERTO!") : "";
            if (status != w.statusText) { w.statusText = status; w.status.text = status; }
            w.height = status.Length > 0 ? 74f : 40f;
        }

        /// <summary>
        /// Las barras de enemigos juntos se apilan: de abajo para arriba, la que pisa a otra sube. El orden tiene
        /// histéresis (dos cabezas a menos de 12 px conservan el del cuadro anterior) y el corrimiento se desliza:
        /// con los enemigos girando alrededor de Kaito las cabezas se cruzaban todo el tiempo y la barra de arriba
        /// saltaba abajo (y su texto, la cinta de Ejecutar, las marcas y el kunai del fijado con ella) en un cuadro.
        /// </summary>
        void Declutter(int n, float dt)
        {
            // primero el orden anterior y después por altura, moviendo solo lo que se separó de verdad
            for (int i = 1; i < n; i++)
            {
                var w = sortBuf[i]; int j = i - 1;
                while (j >= 0 && sortBuf[j].rank > w.rank) { sortBuf[j + 1] = sortBuf[j]; j--; }
                sortBuf[j + 1] = w;
            }
            for (int i = 1; i < n; i++)
            {
                var w = sortBuf[i]; int j = i - 1;
                while (j >= 0 && sortBuf[j].head.y > w.head.y + 12f) { sortBuf[j + 1] = sortBuf[j]; j--; }
                sortBuf[j + 1] = w;
            }
            for (int i = 0; i < n; i++)
            {
                var a = sortBuf[i];
                a.rank = i;
                a.target = a.head.y;
                for (int j = 0; j < i; j++)
                {
                    var b = sortBuf[j];
                    if (Mathf.Abs(a.head.x - b.head.x) < 128f && a.target < b.target + b.height + 4f && a.target + a.height > b.target)
                        a.target = b.target + b.height + 4f;
                }
                float off = a.target - a.head.y;
                a.stack = a.snap ? off : Mathf.MoveTowards(a.stack, off, dt * 500f);
                a.snap = false;
                a.pos = new Vector2(a.head.x, a.head.y + a.stack);
            }
        }

        /// <summary>Apaga los avisos sobre Kaito y las marcas sobre los enemigos que estaban en el aire.</summary>
        void ClearWorldCues()
        {
            foreach (var c in callouts) if (c.active) { c.active = false; c.text.enabled = false; }
            foreach (var m in markers) if (m.active) { m.active = false; m.img.enabled = false; }
        }

        /// <summary>Punto (en el canvas) arriba de todo lo que tiene el enemigo encima: barra, postura y texto.</summary>
        Vector2 StackTop(Enemy e, Vector2 head)
        {
            if (widgetOf.TryGetValue(e, out var w) && w.shown) return new Vector2(w.pos.x, w.pos.y + w.height);
            return head + new Vector2(0f, 24f);
        }

        // ---------------------------------------------------------------- marcas (alerta, imparable, guardia)
        void AddMarker(Enemy e, int kind, Sprite icon, Color c, float size, float life)
        {
            if (e == null || icon == null) return;
            Marker m = null;
            foreach (var x in markers) if (!x.active) { m = x; break; }
            if (m == null)
            {
                var img = UIFactory.Centered("Marker", world, c, Vector2.zero, Vector2.zero, new Vector2(size, size), icon);
                m = new Marker { rt = img.rectTransform, img = img };
                markers.Add(m);
            }
            // una sola marca de cada tipo por enemigo: la nueva reemplaza a la vieja
            foreach (var x in markers) if (x.active && x.e == e && x.kind == kind) x.active = false;
            m.active = true; m.e = e; m.kind = kind; m.t = 0f; m.life = life; m.size = size;
            m.img.sprite = icon; m.img.color = c; m.img.enabled = true;
            m.rt.sizeDelta = new Vector2(size, size);
        }

        float lockMarkerTop;

        void UpdateMarkers(Camera cam, float scale, float dt, float t)
        {
            lockMarkerTop = float.NegativeInfinity;
            for (int i = 0; i < markers.Count; i++)
            {
                var m = markers[i];
                if (!m.active) { if (m.img.enabled) m.img.enabled = false; continue; }
                m.t += dt;
                // el imparable queda mientras dura su aviso (late a 6 Hz hasta el golpe) y después se va
                bool holding = m.kind == MarkUnblockable && m.e != null && m.e.InTell && m.e.StepKind == AttackKind.Unblockable;
                if (holding) m.t = Mathf.Min(m.t, m.life * 0.7f);
                if (m.e == null || m.t > m.life || !m.e.gameObject.activeInHierarchy || !Project(cam, HeadPoint(m.e), scale, out var hp))
                {
                    m.active = false; m.img.enabled = false; continue;
                }
                var top = StackTop(m.e, hp);
                m.rt.anchoredPosition = top + new Vector2(0f, m.size * 0.5f + 6f);
                if (m.e == lockTarget) lockMarkerTop = Mathf.Max(lockMarkerTop, top.y + m.size + 6f);
                float k = m.t / m.life;
                float pop = UIAnim.Pop(m.t, 0.2f, 0.3f, 1.2f);
                if (holding) pop *= 1.06f + 0.06f * Mathf.Sin(t * Mathf.PI * 12f);
                m.rt.localScale = Vector3.one * pop;
                var c = m.img.color; c.a = k > 0.75f ? 1f - (k - 0.75f) / 0.25f : 1f; m.img.color = c;
            }
        }

        public void ShowAlertMark(Enemy e) { if (Settings.ShowParryAids) AddMarker(e, MarkAlert, UISprites.Alert, UIFactory.Gold, 56f, 1.1f); }
        public void ShowDanger(Enemy e) { if (Settings.ShowUnblockableAids) AddMarker(e, MarkUnblockable, UISprites.Unblockable, UIFactory.Crimson, 64f, 1.2f); }
        public void ShowGuardMark(Enemy e) { if (Settings.ShowParryAids) AddMarker(e, MarkGuard, UISprites.Guard, UIFactory.Steel, 48f, 0.7f); }
        public void PulseImbalance(Enemy e) { if (e != null && !(e is Boss)) GetWidget(e).visibleUntil = Time.time + 3f; }
        public void SetLockTarget(Enemy e) { if (e != lockTarget) lockPopT = 0f; lockTarget = e; }
        public void SetInteractPrompt(Interactable i) => interactTarget = i;
        public void HideInteractPrompt() => interactTarget = null;

        // ---------------------------------------------------------------- avisos de combate sobre Kaito
        /// <summary>
        /// Aviso corto pegado a Kaito ("¡FILO DE IRA!", "¡Parry perfecto!", "Instante sombra"): salta, sube un poco
        /// y se apaga en ~1 s, centrado sobre su cabeza, un renglón más arriba que "TEMPRANO / TARDE" (TimingCoach,
        /// mismo pincel y contorno). Antes iba en el centro de la pantalla, encima de los enemigos, y pisaba los
        /// avisos de progreso.
        /// </summary>
        public void ShowCallout(string text, Color c, float life = 1f)
        {
            Callout slot = null;
            foreach (var x in callouts) if (!x.active) { slot = x; break; }
            if (slot == null) { slot = callouts[0]; foreach (var x in callouts) if (x.t > slot.t) slot = x; }
            // los que ya estaban suben un renglón
            foreach (var x in callouts) if (x.active && x != slot) x.lift += 44f;
            slot.active = true; slot.t = 0f; slot.life = Mathf.Max(0.6f, life); slot.lift = 0f;
            slot.text.text = text; slot.text.color = c; slot.text.enabled = true;
        }

        void UpdateCallouts(Camera cam, float scale, PlayerController p, float dt)
        {
            bool visible = Project(cam, p.transform.position + Vector3.up * 2.9f, scale, out var anchor);
            foreach (var c in callouts)
            {
                if (!c.active) continue;
                c.t += dt;
                if (c.t >= c.life || !visible) { c.active = false; c.text.enabled = false; continue; }
                float k = c.t / c.life;
                c.rt.anchoredPosition = anchor + new Vector2(0f, 30f * UIAnim.OutCubic(k) + c.lift);
                c.rt.localScale = Vector3.one * UIAnim.Pop(c.t, 0.1f, 0.6f, 1.15f);
                var col = c.text.color; col.a = c.t > c.life - 0.6f ? (c.life - c.t) / 0.6f : 1f; c.text.color = col;
            }
        }
    }
}
