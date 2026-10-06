using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>Paleta del fuego de los braseros: naranja (Acto 1), violeta (Acto 2, la sombra suelta).</summary>
    public enum FlameStyle { Fire, Violet }

    /// <summary>
    /// Fuego de los 8 braseros del patio de Kokuyō (prop brazier_kage, que no trae llamas en la malla). Por brasero:
    /// lenguas de fuego facetadas (Nindo/Fire, se mueven en el shader), cama de brasas, chispas que suben, una
    /// luz puntual que titila y un hilo de humo cuando está frío. Se encienden en secuencia en la presentación,
    /// se vuelven violetas cuando la sombra se suelta y se apagan uno por uno en el eclipse (con humo y siseo).
    /// Cada brasero encendido crepita (loop "brazier_crackle" en 3D, sigue el tamaño de la llama): el patio suena
    /// vivo y el eclipse se oye apagarse.
    /// Los índices van en sentido horario desde el norte: el brasero 0 queda a la derecha de la pantalla (a la
    /// izquierda de Kokuyō, que mira al sur).
    /// </summary>
    public class Braziers : MonoBehaviour
    {
        /// <summary>Altura del fuego sobre la base del brasero (props_dojo.BRAZIER_FIRE_Z).</summary>
        public const float FireHeight = 1.12f;
        public float LightIntensity = 2f;
        public float LightRange = 7f;
        /// <summary>A más de esta distancia de Kaito las luces se apagan (el fuego se sigue viendo por el bloom).</summary>
        public float LightCullDistance = 45f;
        /// <summary>Volumen del crepitar de un brasero encendido (antes de los ajustes de audio).</summary>
        public float CrackleVolume = 0.45f;

        struct Palette
        {
            public Color outer, mid, core, light, ember;
            public static Palette Lerp(Palette a, Palette b, float t) => new Palette
            {
                outer = Color.Lerp(a.outer, b.outer, t), mid = Color.Lerp(a.mid, b.mid, t), core = Color.Lerp(a.core, b.core, t),
                light = Color.Lerp(a.light, b.light, t), ember = Color.Lerp(a.ember, b.ember, t),
            };
        }

        // colores HDR (el proyecto está en espacio gamma: van tal cual al shader). El tonemapping ACES de ScreenFX
        // lava hacia el blanco todo canal que pase de ~1.5: el canal dominante va alto (bloom) y los otros bajos,
        // si no el fuego naranja se ve crema y el violeta lila (medido con la curva ACES: afuera 0.91/0.56/0.13)
        static readonly Palette FirePal = new Palette
        {
            outer = new Color(2.0f, 0.42f, 0.1f), mid = new Color(2.4f, 0.95f, 0.2f), core = new Color(3.0f, 2.3f, 0.9f),
            light = new Color(1f, 0.48f, 0.16f), ember = new Color(1f, 0.62f, 0.25f),
        };
        static readonly Palette VioletPal = new Palette
        {
            outer = new Color(0.75f, 0.18f, 2.2f), mid = new Color(1.2f, 0.55f, 2.6f), core = new Color(2.2f, 1.7f, 3.0f),
            light = new Color(0.75f, 0.54f, 1f), ember = new Color(0.8f, 0.55f, 1f),
        };

        class Item
        {
            public Transform anchor, fire;
            public MeshRenderer flame;
            public Light light;
            public ParticleSystem embers, wisp;
            public AudioSource crackle;
            public float size, target, flare, bed, seed, pitch;
            public bool lit;
        }

        static readonly int IdColor = Shader.PropertyToID("_Color"), IdMid = Shader.PropertyToID("_Mid"), IdCore = Shader.PropertyToID("_Core"),
            IdSize = Shader.PropertyToID("_Size"), IdBed = Shader.PropertyToID("_Bed"), IdSeed = Shader.PropertyToID("_Seed");
        static Mesh flameMesh;

        readonly List<Item> items = new List<Item>();
        MaterialPropertyBlock mpb;
        Material flameMat;
        Palette pal = FirePal, palFrom = FirePal, palTo = FirePal;
        float palT = 1f, palDur;
        Coroutine sequence;

        public int Count => items.Count;
        public FlameStyle Style { get; private set; } = FlameStyle.Fire;

        // ================================================================== creación
        /// <summary>Arma el fuego sobre cada brasero (los ordena en sentido horario desde el norte de 'center').</summary>
        public static Braziers Create(Transform parent, IList<Transform> anchors, Vector3 center)
        {
            var go = new GameObject("Braseros");
            go.transform.SetParent(parent, false);
            var b = go.AddComponent<Braziers>();
            var sorted = new List<Transform>(anchors);
            sorted.RemoveAll(t => t == null);
            sorted.Sort((x, y) => Bearing(x.position - center).CompareTo(Bearing(y.position - center)));
            foreach (var a in sorted) b.Add(a);
            return b;
        }

        static float Bearing(Vector3 d) => (Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg + 360f) % 360f;

        void Awake()
        {
            mpb = new MaterialPropertyBlock();
            var sh = Resources.Load<Shader>("Shaders/NindoFire");
            if (sh != null && sh.isSupported) flameMat = new Material(sh) { name = "Nindo_BrazierFire" };
            else Debug.LogWarning("[Nindo] No compila Nindo/Fire: los braseros quedan sin llamas (solo luz y chispas).");
        }

        void OnDestroy() { if (flameMat != null) Destroy(flameMat); }

        void Add(Transform anchor)
        {
            var it = new Item { anchor = anchor, seed = Random.Range(0f, 100f) };
            var fire = new GameObject("Fuego_" + items.Count).transform;
            fire.SetParent(transform, false);
            fire.position = anchor.position + anchor.up * FireHeight * anchor.lossyScale.y;
            it.fire = fire;
            if (flameMat != null)
            {
                var fg = new GameObject("Llamas");
                fg.transform.SetParent(fire, false);
                fg.transform.localRotation = Quaternion.Euler(0f, Random.Range(0f, 360f), 0f);
                fg.AddComponent<MeshFilter>().sharedMesh = FlameMesh;
                it.flame = fg.AddComponent<MeshRenderer>();
                it.flame.sharedMaterial = flameMat;
                it.flame.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                it.flame.receiveShadows = false;
                it.flame.lightProbeUsage = UnityEngine.Rendering.LightProbeUsage.Off;
                it.flame.enabled = false;
            }
            var lg = new GameObject("Luz");
            lg.transform.SetParent(fire, false);
            lg.transform.localPosition = new Vector3(0f, 0.45f, 0f);
            it.light = lg.AddComponent<Light>();
            it.light.type = LightType.Point;
            it.light.shadows = LightShadows.None;
            it.light.range = LightRange;
            it.light.intensity = 0f;
            it.light.enabled = false;
            it.embers = MakeEmbers(fire);
            it.wisp = FXFactory.Smoke(fire, 0.55f);
            it.wisp.transform.localPosition = new Vector3(0f, 0.05f, 0f);
            it.crackle = MakeCrackle(fire, it);
            items.Add(it);
            Refresh(it, 0f);
        }

        /// <summary>Loop de fuego en 3D (corto alcance: se oye el brasero que Kaito tiene cerca, no los ocho juntos).</summary>
        static AudioSource MakeCrackle(Transform fire, Item it)
        {
            var entry = Game.LoadContent() != null ? Game.LoadContent().Sfx("brazier_crackle") : null;
            if (entry == null || entry.clips == null || entry.clips.Length == 0 || entry.clips[0] == null) return null;
            var s = fire.gameObject.AddComponent<AudioSource>();
            s.clip = entry.clips[0];
            s.loop = true; s.playOnAwake = false; s.volume = 0f;
            s.spatialBlend = 0.85f; s.rolloffMode = AudioRolloffMode.Linear; s.minDistance = 2f; s.maxDistance = 16f; s.dopplerLevel = 0f;
            // cada uno en otro punto del loop y otro tono: ocho copias juntas no suenan en fase
            it.pitch = Random.Range(0.9f, 1.1f);
            s.time = Random.Range(0f, s.clip.length * 0.9f);
            return s;
        }

        static ParticleSystem MakeEmbers(Transform parent)
        {
            var ps = FXFactory.NewSystem("Chispas", parent);
            var m = ps.main;
            m.loop = true; m.duration = 2f; m.playOnAwake = true;
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.7f, 1.5f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.6f, 1.5f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.03f, 0.07f);
            m.gravityModifier = -0.15f;
            m.maxParticles = 60;
            var em = ps.emission; em.rateOverTime = 0f;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Cone; sh.angle = 14f; sh.radius = 0.2f;
            sh.rotation = new Vector3(-90f, 0f, 0f);
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.6f; noise.frequency = 1.2f;
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(new Color(1f, 0.5f, 0.3f), 1f) },
                      new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(0.8f, 0.6f), new GradientAlphaKey(0f, 1f) });
            col.color = g;
            ps.Play();
            return ps;
        }

        /// <summary>
        /// Lenguas facetadas como las de los props (props_misc.fire_cluster): una central, tres rojas afuera que se
        /// abren y dos claras adentro, más una cama de brasas. Ver los canales de color en Nindo/Fire.
        /// </summary>
        static Mesh FlameMesh
        {
            get
            {
                if (flameMesh != null) return flameMesh;
                var v = new List<Vector3>();
                var c = new List<Color>();
                var t = new List<int>();
                // cama de brasas: domo bajo de 7 lados (alfa 0)
                int n = 7, c0 = v.Count;
                v.Add(new Vector3(0f, 0.06f, 0f)); c.Add(new Color(0f, 0.6f, 0f, 0f));
                for (int i = 0; i < n; i++)
                {
                    float a = i * Mathf.PI * 2f / n;
                    v.Add(new Vector3(Mathf.Cos(a) * 0.44f, -0.01f, Mathf.Sin(a) * 0.44f));
                    c.Add(new Color(0f, 0.3f, 0f, 0f));
                }
                for (int i = 0; i < n; i++) t.AddRange(new[] { c0, c0 + 1 + (i + 1) % n, c0 + 1 + i });
                Tongue(v, c, t, Vector3.zero, 0.3f, 0.85f, 5, 0.5f, new Vector2(0.03f, -0.02f), 0.1f);
                for (int k = 0; k < 3; k++)
                {
                    float a = Mathf.Deg2Rad * (30f + 120f * k);
                    var d = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
                    Tongue(v, c, t, new Vector3(d.x * 0.25f, 0.01f, d.y * 0.25f), 0.15f, 0.55f, 4, 0f, d * 0.14f, 0.3f + 0.2f * k);
                }
                for (int k = 0; k < 2; k++)
                {
                    float a = Mathf.Deg2Rad * (100f + 180f * k);
                    var d = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
                    Tongue(v, c, t, new Vector3(d.x * 0.12f, 0.03f, d.y * 0.12f), 0.14f, 0.68f, 4, 1f, d * 0.08f, 0.75f + 0.2f * k);
                }
                flameMesh = new Mesh { name = "FuegoBrasero" };
                flameMesh.SetVertices(v);
                flameMesh.SetColors(c);
                flameMesh.SetTriangles(t, 0);
                flameMesh.RecalculateNormals();
                flameMesh.bounds = new Bounds(new Vector3(0f, 0.6f, 0f), new Vector3(1.4f, 1.6f, 1.4f));   // con el vaivén
                return flameMesh;
            }
        }

        static void Tongue(List<Vector3> v, List<Color> c, List<int> t, Vector3 b, float r, float h, int sides, float layer, Vector2 lean, float phase01)
        {
            var prof = new[] { new Vector2(r, 0f), new Vector2(r * 1.25f, h * 0.3f), new Vector2(r * 0.5f, h * 0.66f) };
            int start = v.Count;
            for (int k = 0; k < prof.Length; k++)
            {
                float y = prof[k].y, k01 = y / h, tw = 0.7f * k + phase01 * 6.28f;
                for (int i = 0; i < sides; i++)
                {
                    float a = tw + i * Mathf.PI * 2f / sides;
                    v.Add(new Vector3(b.x + Mathf.Cos(a) * prof[k].x + lean.x * k01 * k01, b.y + y, b.z + Mathf.Sin(a) * prof[k].x + lean.y * k01 * k01));
                    c.Add(new Color(k01, layer, phase01, 1f));
                }
            }
            int tip = v.Count;
            v.Add(new Vector3(b.x + lean.x, b.y + h, b.z + lean.y));
            c.Add(new Color(1f, layer, phase01, 1f));
            for (int k = 0; k < prof.Length - 1; k++)
                for (int i = 0; i < sides; i++)
                {
                    int a0 = start + k * sides + i, a1 = start + k * sides + (i + 1) % sides;
                    int b0 = a0 + sides, b1 = a1 + sides;
                    t.AddRange(new[] { a0, b0, a1, a1, b0, b1 });
                }
            int last = start + (prof.Length - 1) * sides;
            for (int i = 0; i < sides; i++) t.AddRange(new[] { last + i, tip, last + (i + 1) % sides });
        }

        // ================================================================== API
        public bool IsLit(int i) => Valid(i) && items[i].lit;
        public Vector3 FirePosition(int i) => Valid(i) ? items[i].fire.position : transform.position;
        bool Valid(int i) => i >= 0 && i < items.Count;

        /// <summary>Enciende un brasero: las llamas nacen de la brasa con un estallido de chispas y la luz salta.</summary>
        public void Ignite(int i, bool flare = true)
        {
            if (!Valid(i)) return;
            var it = items[i];
            if (it.lit) return;
            it.lit = true;
            it.target = 1f;
            it.bed = 1f;
            if (flare) Flare(i, 1f);
            Game.Audio?.Play("brazier_ignite", it.fire.position, 0.8f);
        }

        /// <summary>Apaga un brasero: las llamas se hunden, una bocanada de humo, siseo y unas brasas que se apagan solas.</summary>
        public void Extinguish(int i, bool puff = true)
        {
            if (!Valid(i)) return;
            var it = items[i];
            if (!it.lit) return;
            it.lit = false;
            it.target = 0f;
            it.bed = 0.7f;
            if (puff)
            {
                Game.FX?.SmokePuff(it.fire.position + Vector3.up * 0.3f, 0.75f);
                Game.Audio?.Play("brazier_out", it.fire.position, 0.8f);
            }
        }

        /// <summary>Un golpe de fuego (chispas y luz) sin cambiar el estado: p. ej. cuando Kokuyō desenvaina.</summary>
        public void Flare(int i, float strength = 1f)
        {
            if (!Valid(i)) return;
            var it = items[i];
            it.flare = Mathf.Max(it.flare, strength);
            if (it.embers != null)
            {
                var ep = new ParticleSystem.EmitParams();
                int n = Mathf.RoundToInt(22 * strength);
                for (int k = 0; k < n; k++)
                {
                    ep.velocity = new Vector3(Random.Range(-1.2f, 1.2f), Random.Range(2.2f, 4.5f), Random.Range(-1.2f, 1.2f));
                    ep.startColor = pal.ember;
                    it.embers.Emit(ep, 1);
                }
            }
        }

        public void FlareAll(float strength = 1f) { for (int i = 0; i < items.Count; i++) if (items[i].lit) Flare(i, strength); }

        /// <summary>Enciende todos en secuencia ('interval' s entre uno y otro, sentido horario desde 'start'). Devuelve cuánto tarda.</summary>
        public float IgniteAll(float interval = 0.12f, int start = 0, bool clockwise = true) => Run(Order(start, clockwise), interval, true);

        /// <summary>Enciende de a pares desde el más cercano a 'origin' (la ola sale del jefe y rodea el patio).</summary>
        public float IgniteFrom(Vector3 origin, float interval = 0.12f) => Run(OrderFrom(origin), interval, true);

        /// <summary>Apaga todos en secuencia (eclipse: 0.18 s entre uno y otro). Devuelve cuánto tarda.</summary>
        public float ExtinguishAll(float interval = 0.18f, int start = 0, bool clockwise = true) => Run(Order(start, clockwise), interval, false);

        public float ExtinguishFrom(Vector3 origin, float interval = 0.18f) => Run(OrderFrom(origin), interval, false);

        /// <summary>Cambia el color de todos los fuegos (y de sus luces y chispas) en 'seconds'.</summary>
        public void SetStyle(FlameStyle style, float seconds = 1f)
        {
            Style = style;
            palFrom = pal;
            palTo = style == FlameStyle.Violet ? VioletPal : FirePal;
            palDur = Mathf.Max(0f, seconds);
            palT = palDur > 0f ? 0f : 1f;
            if (palDur <= 0f) pal = palTo;
        }

        /// <summary>Estado inmediato (reintentos): todos encendidos o todos fríos, sin humo ni chispas de transición.</summary>
        public void SetAll(bool lit, FlameStyle style = FlameStyle.Fire)
        {
            if (sequence != null) { StopCoroutine(sequence); sequence = null; }
            SetStyle(style, 0f);
            foreach (var it in items)
            {
                it.lit = lit;
                it.size = it.target = lit ? 1f : 0f;
                it.bed = lit ? 1f : 0f;
                it.flare = 0f;
                if (it.embers != null) it.embers.Clear();
                Refresh(it, 0f);
            }
        }

        List<int> Order(int start, bool clockwise)
        {
            var o = new List<int>();
            int n = items.Count;
            for (int k = 0; k < n; k++) o.Add(((clockwise ? start + k : start - k) % n + n) % n);
            return o;
        }

        List<int> OrderFrom(Vector3 origin)
        {
            var o = new List<int>();
            for (int i = 0; i < items.Count; i++) o.Add(i);
            o.Sort((a, b) => (items[a].fire.position - origin).sqrMagnitude.CompareTo((items[b].fire.position - origin).sqrMagnitude));
            return o;
        }

        float Run(List<int> order, float interval, bool ignite)
        {
            if (sequence != null) StopCoroutine(sequence);
            sequence = StartCoroutine(Sequence(order, interval, ignite));
            return order.Count * interval;
        }

        IEnumerator Sequence(List<int> order, float interval, bool ignite)
        {
            foreach (int i in order)
            {
                if (ignite) Ignite(i); else Extinguish(i);
                // tiempo real: la secuencia acompaña cinemáticas y la cámara lenta del cambio de fase
                if (interval > 0f) yield return new WaitForSecondsRealtime(interval);
            }
            sequence = null;
        }

        // ================================================================== cada frame
        void Update()
        {
            float dt = Time.deltaTime;
            if (palT < 1f)
            {
                palT = Mathf.Clamp01(palT + Time.unscaledDeltaTime / palDur);
                pal = Palette.Lerp(palFrom, palTo, Mathf.SmoothStep(0f, 1f, palT));
            }
            Vector3 player = Game.Player != null ? Game.Player.transform.position : transform.position;
            float vol = CrackleVolume * Settings.MasterVolume * Settings.SfxVolume;
            // como los efectos de AudioManager, en cámara lenta suena más grave; el fuego violeta, un poco más grave
            // siempre (no es fuego de verdad). violet: cuánto violeta hay, siguiendo el fundido de SetStyle
            float k = Mathf.SmoothStep(0f, 1f, palT);
            float violet = Style == FlameStyle.Violet ? k : 1f - k;
            float pitch = Mathf.Lerp(0.55f, 1f, Mathf.Clamp01(Game.Time != null ? Game.Time.SlowMoScale : 1f)) * Mathf.Lerp(1f, 0.82f, violet);
            foreach (var it in items)
            {
                // las llamas nacen rápido (con el empujón del destello) y se hunden más rápido al apagarse
                it.size = Mathf.MoveTowards(it.size, it.target, dt * (it.target > it.size ? 3.2f : 4.5f));
                it.flare = Mathf.Max(0f, it.flare - dt * 3f);
                if (!it.lit) it.bed = Mathf.Max(0f, it.bed - dt / 6f);
                Refresh(it, (player - it.fire.position).sqrMagnitude);
                if (it.crackle != null)
                {
                    it.crackle.volume = vol * it.size * (1f + 0.6f * it.flare);
                    it.crackle.pitch = it.pitch * pitch;
                    bool on = it.crackle.volume > 0.001f;
                    if (on && !it.crackle.isPlaying) it.crackle.Play();
                    else if (!on && it.crackle.isPlaying) it.crackle.Pause();
                }
            }
        }

        void Refresh(Item it, float playerSqr)
        {
            float shown = it.size * (1f + 0.3f * it.flare);
            if (it.flame != null)
            {
                bool vis = shown > 0.01f || it.bed > 0.01f;
                it.flame.enabled = vis;
                if (vis)
                {
                    mpb.SetColor(IdColor, pal.outer);
                    mpb.SetColor(IdMid, pal.mid);
                    mpb.SetColor(IdCore, pal.core);
                    mpb.SetFloat(IdSize, shown);
                    mpb.SetFloat(IdBed, Mathf.Max(it.bed, it.size));
                    mpb.SetFloat(IdSeed, it.seed);
                    it.flame.SetPropertyBlock(mpb);
                }
            }
            float flick = 0.85f + 0.25f * Mathf.PerlinNoise(Time.time * 6f, it.seed);
            float inten = LightIntensity * (it.size * flick + 1.5f * it.flare) + 0.4f * it.bed * (1f - it.size);
            bool near = playerSqr < LightCullDistance * LightCullDistance;
            it.light.enabled = near && inten > 0.02f;
            it.light.intensity = inten;
            it.light.color = Color.Lerp(pal.light, pal.light * new Color(1f, 0.75f, 0.6f), 1f - it.size);
            it.light.range = LightRange * (0.6f + 0.4f * Mathf.Max(it.size, it.bed));
            if (it.embers != null)
            {
                var em = it.embers.emission; em.rateOverTime = 7f * it.size;
                var m = it.embers.main; m.startColor = pal.ember;
            }
            // humo fino cuando está frío o con las brasas recién apagadas
            if (it.wisp != null) { var em = it.wisp.emission; em.rateOverTime = it.lit ? 0f : 1.2f + 2.5f * it.bed; }
        }
    }
}
