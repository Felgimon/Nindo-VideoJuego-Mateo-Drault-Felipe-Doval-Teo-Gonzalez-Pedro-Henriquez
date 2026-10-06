using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Nindo
{
    /// <summary>
    /// La Cascada Kohan, detrás de la arena de Mizuchi. El acantilado es un prop estático (kohan_falls_cliff,
    /// Tools/Blender/props/props_falls.py); el agua la arma este componente en runtime a partir de los datos que
    /// el prop escribe en el manifest ("falls": labios de cada cortina, línea de caída, rocas del pozo, cintas
    /// del desagüe). WorldBuilder lo engancha a los props con la etiqueta 'waterfall'.
    ///
    /// Con la cámara de combate (pitch 43-47, FOV 30) el borde de arriba de la imagen toca el agua ~12-15 m más allá
    /// de Kaito; la sub-zona 'lago_cascada' baja la cámara 4° y la aleja 1 m (StoryText.ConfigureZone), y aun así
    /// desde el juego se ven sobre todo el pie de las cortinas, el pozo y el rocío. Por eso la caída se vende con lo
    /// que queda en cuadro: hervor, coronas de gotas, la nube de rocío que cruza la baranda norte, cola de gallo,
    /// llovizna con viento sobre la plataforma, niebla que corre hacia la arena, luz fría de relleno desde el
    /// pozo y el rugido 3D que crece por toda la pasarela. La altura entera (42 m) se ve en las tomas de jefe,
    /// con columnas de niebla que suben pegadas a la roca y el arcoíris de luna en el rocío.
    ///
    ///  * Cortinas: una malla (dos capas: lámina de atrás + tiras sueltas adelante) con shader Nindo/Waterfall.
    ///  * Partículas Shuriken en espacio mundo, emitidas a mano sobre los labios y la línea de caída (cada gota sale
    ///    con la velocidad y el tiempo de vuelo de su labio). Tope total ~1.400 vivas.
    ///  * Intensity (1 en la fase 1, 1.4 en la crecida de la fase 2) y Surge(mult, s) para los golpes de agua del
    ///    cambio de fase; Corruption tiñe de violeta la parte alta; Flood = capa de agua sobre la plataforma.
    ///  * LOD: a más de 110 m de Kaito se apagan los emisores y la luz; en calidad baja, la mitad de partículas,
    ///    sin llovizna y una sola lámina de niebla.
    /// </summary>
    public class KohanFalls : MonoBehaviour
    {
        // ------------------------------------------------------------------ datos del manifest (falls_layout.falls_meta)
        [Serializable] class SheetData { public string name; public float[] lip; public int layers; }
        [Serializable] class RibbonData { public float[] pts; }
        [Serializable]
        class FallsData
        {
            public SheetData[] sheets; public float[] center; public float[] arena; public float deckRadius; public float deckHeight;
            public float v0; public float[] rocks; public float[] plunge; public RibbonData[] ribbons; public float ribbonWidth;
        }
        [Serializable] class PropFalls { public string id; public FallsData falls; }
        [Serializable] class Manifest { public PropFalls[] props; }

        class Sheet
        {
            public string name;
            public Vector3[] lip, dir, plunge;     // mundo
            public float[] fall, arc;
            public float length, weight;
            public int layers;
        }

        const float G = 9.81f;
        const float LodDistance = 110f;
        const float FillIntensity = 48f;
        const float RoarMax = 140f;
        // con snow_shade (0.725, 0.78, 0.847) el rocío era del mismo gris que la nieve de la montaña
        static readonly Color MistColor = new Color(0.7f, 0.8f, 0.86f);
        static readonly Color WaterTint = new Color(0.58f, 0.77f, 0.88f);
        static readonly Color FillColor = new Color(0.663f, 0.831f, 0.902f);  // ice

        public static KohanFalls Instance { get; private set; }

        // ------------------------------------------------------------------ API (para MizuchiArena / el jefe)
        /// <summary>Caudal: 1 en la fase 1, 1.4 en la crecida de la fase 2. Se suaviza solo.</summary>
        public float Intensity { get => intensityTarget; set => intensityTarget = Mathf.Clamp(value, 0.5f, 2.5f); }
        /// <summary>Tinte violeta del sello en la parte alta de las cortinas (transición a la fase 2).</summary>
        public float Corruption { get => corruptTarget; set => corruptTarget = Mathf.Clamp01(value); }
        /// <summary>Multiplica el arcoíris de luna (x2 en la fase 3).</summary>
        public float MoonbowBoost { get; set; } = 1f;
        /// <summary>Qué despeja la niebla además de Kaito (por defecto, el jefe activo).</summary>
        public Transform BossFocus { get; set; }
        public FloodSheet Flood { get; private set; }
        public Vector3 PlungeCenter { get; private set; }
        /// <summary>Mitad del labio de la cortina central (lo más alto de la caída): a dónde termina mirando la toma
        /// de presentación.</summary>
        public Vector3 LipCenter { get; private set; }
        public Vector3 ArenaCenter { get; private set; }
        public float DeckY { get; private set; }
        public float WaterY => transform.position.y;
        public float CurrentIntensity => intensity;
        /// <summary>Kaito está cerca: emisores, luz y viento encendidos.</summary>
        public bool Active { get; private set; }

        /// <summary>Golpe de agua: el caudal se multiplica por 'mult' (sube en 0.3 s, se mantiene y baja en 1 s).</summary>
        public void Surge(float mult, float seconds)
        {
            surgeMult = Mathf.Max(1f, mult);
            surgeStart = Time.time;
            surgeEnd = Time.time + Mathf.Max(0.3f, seconds);
        }

        /// <summary>Vuelve todo al estado de la fase 1 (reintento después de morir).</summary>
        public void ResetFight()
        {
            // con Mizuchi vencido la cascada queda como la deje la secuencia de después (B3): morir en otra zona
            // no tiene que devolverla a la pelea
            if (Game.Save != null && Game.Save.HasFlag(Flags.Boss("mizuchi"))) return;
            intensityTarget = 1f; surgeEnd = 0f; corruptTarget = 0f; MoonbowBoost = 1f;
            Flood?.Drain(0f);
        }

        /// <summary>Lo llama WorldBuilder para los props con la etiqueta 'waterfall' (el agua no va en el lote estático).</summary>
        public static KohanFalls Attach(GameObject prop, Transform parent)
        {
            var data = Load(prop.name);
            if (data == null)
            {
                Debug.LogWarning($"[Nindo] '{prop.name}' tiene la etiqueta 'waterfall' pero el manifest no trae sus datos 'falls'.");
                return null;
            }
            var go = new GameObject("KohanFalls");
            go.transform.SetParent(parent, false);
            go.transform.SetPositionAndRotation(prop.transform.position, prop.transform.rotation);
            var f = go.AddComponent<KohanFalls>();
            f.Build(data);
            return f;
        }

        static FallsData Load(string id)
        {
            var t = Game.Content != null ? Game.Content.propsManifest : null;
            if (t == null) return null;
            try
            {
                var m = JsonUtility.FromJson<Manifest>(t.text);
                if (m?.props != null)
                    foreach (var p in m.props)
                        if (p.id == id && p.falls != null && p.falls.sheets != null && p.falls.sheets.Length > 0) return p.falls;
            }
            catch (Exception e) { Debug.LogWarning("[Nindo] Datos de la cascada inválidos: " + e.Message); }
            return null;
        }

        // ------------------------------------------------------------------ estado
        readonly List<Sheet> sheets = new List<Sheet>();
        float totalWeight;
        Vector3[] plungeLine;
        float[] plungeW;
        float plungeWTotal;
        float v0 = 1.2f;
        Vector3 windDir = Vector3.back;

        float intensityTarget = 1f, intensity = 1f, surgeMult = 1f, surgeStart, surgeEnd;
        float corruptTarget, corrupt;
        float flowPhase;        // segundos de flujo acumulados (dt * caudal): fase de las vetas, el hervor y las cintas
        bool audioPaused;
        bool lowQuality;
        float qualityTimer, volumeTimer, volumeTarget, gustTimer, gust, gustDur, gustAngle;

        Material curtainMat, poolMat, ribbonMat, sprayMat, moonbowMat;
        Material[] mistMats;
        Transform[] mistSheets;
        Vector2[] mistScroll;
        Light fill;
        AudioSource roar, hiss;
        NindoContent.AudioEntry roarEntry, hissEntry;
        readonly List<Mesh> meshes = new List<Mesh>();
        readonly List<Material> materials = new List<Material>();

        ParticleSystem clumps, crowns, boil, cloud, rooster, glints, rolling, columns, drizzle, drizzleGlints;
        ParticleSystem[] drizzles;
        readonly List<ParticleSystem> systems = new List<ParticleSystem>();
        float aClump, aBoil, aCloud, aRooster, aGlint, aRolling, aColumn;

        static readonly int IdFlowPhase = Shader.PropertyToID("_FlowPhase"), IdIntensity = Shader.PropertyToID("_Intensity"),
            IdTurb = Shader.PropertyToID("_Turbulence"), IdCorrupt = Shader.PropertyToID("_Corrupt"), IdPoolFlow = Shader.PropertyToID("_Flow"),
            IdScroll = Shader.PropertyToID("_Scroll"), IdAlphaStep = Shader.PropertyToID("_AlphaStep"), IdBaseColor = Shader.PropertyToID("_BaseColor"),
            IdColor = Shader.PropertyToID("_Color"), IdPlayer = Shader.PropertyToID("_NindoPlayerPos"), IdBoss = Shader.PropertyToID("_NindoBossPos"),
            IdWind = Shader.PropertyToID("_NindoFallsWind"), IdMainTex = Shader.PropertyToID("_BaseMap");

        void OnEnable()
        {
            Instance = this;
            GameEvents.PlayerRespawned += ResetFight;
        }

        void OnDisable()
        {
            GameEvents.PlayerRespawned -= ResetFight;
            if (Instance == this) Instance = null;
            Shader.SetGlobalVector(IdBoss, Vector4.zero);
        }

        void OnDestroy()
        {
            foreach (var m in meshes) if (m != null) Destroy(m);
            foreach (var m in materials) if (m != null) Destroy(m);
        }

        // ================================================================== construcción
        void Build(FallsData d)
        {
            v0 = d.v0 > 0f ? d.v0 : 1.2f;
            Vector3 centerL = V3(d.center, 0);
            foreach (var sd in d.sheets) sheets.Add(MakeSheet(sd, centerL));
            foreach (var s in sheets) totalWeight += s.weight;
            Vector3 pc = Vector3.zero; float pw = 0f;
            foreach (var s in sheets)
                if (s.name == "center") foreach (var p in s.plunge) { pc += p; pw += 1f; }
            if (pw == 0f) foreach (var s in sheets) foreach (var p in s.plunge) { pc += p; pw += 1f; }
            PlungeCenter = pc / Mathf.Max(1f, pw);
            LipCenter = PlungeCenter + Vector3.up * 30f;
            foreach (var sh in sheets)
                if (sh.name == "center" && sh.lip.Length > 0) LipCenter = sh.lip[sh.lip.Length / 2];
            ArenaCenter = transform.TransformPoint(V3(d.arena, 0));
            DeckY = WaterY + (d.deckHeight > 0f ? d.deckHeight : 1f);
            windDir = Flat(ArenaCenter - PlungeCenter);
            BuildPlungeLine(d);

            BuildCurtain();
            BuildPool(d);
            BuildRibbons(d);
            BuildMist();
            BuildParticles();
            BuildMoonbow();
            BuildLight();
            BuildAudio();
            Flood = FloodSheet.Create(transform, new Vector3(ArenaCenter.x, DeckY, ArenaCenter.z), d.deckRadius > 0f ? d.deckRadius : 10.6f);
            Flood.SetWet(0.55f, 0f);   // el rocío ya moja la plataforma: brilla y la llovizna deja anillitos
            Flood.SetSpraySource(PlungeCenter, 22f);
            ApplyQuality();
            Update();
        }

        static Vector3 V3(float[] a, int i) => a != null && a.Length >= i + 3 ? new Vector3(a[i], a[i + 1], a[i + 2]) : Vector3.zero;
        static Vector3 Flat(Vector3 v) { v.y = 0f; return v.sqrMagnitude > 1e-6f ? v.normalized : Vector3.forward; }

        Sheet MakeSheet(SheetData sd, Vector3 centerL)
        {
            int n = sd.lip.Length / 3;
            var s = new Sheet { name = sd.name, layers = Mathf.Max(1, sd.layers), lip = new Vector3[n], dir = new Vector3[n], plunge = new Vector3[n], fall = new float[n], arc = new float[n] };
            for (int i = 0; i < n; i++)
            {
                Vector3 pl = V3(sd.lip, i * 3);
                Vector3 dl = Flat(centerL - pl);
                s.lip[i] = transform.TransformPoint(pl);
                s.dir[i] = transform.TransformDirection(dl);
                s.fall[i] = Mathf.Sqrt(2f * Mathf.Max(0.05f, pl.y) / G);
                s.plunge[i] = transform.TransformPoint(pl + dl * (v0 * s.fall[i]) + Vector3.down * pl.y);
                s.arc[i] = i == 0 ? 0f : s.arc[i - 1] + Vector3.Distance(s.lip[i], s.lip[i - 1]);
            }
            s.length = Mathf.Max(0.1f, s.arc[n - 1]);
            // cuánta agua emite: el ancho, y las cortinas dobles el doble; las altas se ven más
            s.weight = s.length * s.layers * Mathf.Lerp(0.7f, 1.2f, Mathf.InverseLerp(18f, 42f, s.lip[0].y - WaterY));
            return s;
        }

        void BuildPlungeLine(FallsData d)
        {
            int n = d.plunge != null ? d.plunge.Length / 3 : 0;
            plungeLine = new Vector3[n];
            plungeW = new float[n];
            for (int i = 0; i < n; i++)
            {
                plungeLine[i] = transform.TransformPoint(new Vector3(d.plunge[i * 3], 0f, d.plunge[i * 3 + 1]));
                plungeW[i] = d.plunge[i * 3 + 2];
                plungeWTotal += plungeW[i];
            }
        }

        // ------------------------------------------------------------------ cortinas
        void BuildCurtain()
        {
            var V = new List<Vector3>(); var C = new List<Color>(); var U = new List<Vector2>(); var T = new List<int>();
            var rng = new System.Random(4217);
            // la lámina de atrás de TODAS las cortinas primero: el orden de los triángulos es el orden de mezcla
            foreach (var s in sheets) AddSheet(s, rng, V, C, U, T);
            foreach (var s in sheets) if (s.layers > 1) AddStrips(s, rng, V, C, U, T);
            var mesh = new Mesh { name = "KohanFallsCurtain", indexFormat = V.Count > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
            mesh.SetVertices(V); mesh.SetColors(C); mesh.SetUVs(0, U); mesh.SetTriangles(T, 0);
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            // el shader la hincha y la mece (~0.8 m): margen para que no se recorte en el borde de la pantalla
            var cb = mesh.bounds; cb.Expand(2f); mesh.bounds = cb;
            meshes.Add(mesh);
            var sh = Resources.Load<Shader>("Shaders/NindoWaterfall");
            if (sh != null && sh.isSupported) curtainMat = new Material(sh) { name = "KohanFallsCurtain" };
            else curtainMat = FallbackCurtain();
            materials.Add(curtainMat);
            var go = new GameObject("Curtains");
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = curtainMat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
        }

        /// <summary>Lámina de atrás: una columna de vértices por punto del labio; filas parejas en tiempo de vuelo
        /// (más 2 filas del agua que llega al labio). El pie sigue 35 cm bajo el agua, dentro del hervor.</summary>
        void AddSheet(Sheet s, System.Random rng, List<Vector3> V, List<Color> C, List<Vector2> U, List<int> T)
        {
            const int Rows = 16;
            const float Approach = 1.4f;
            int n = s.lip.Length;
            int cols = Rows + 3;
            int baseIndex = V.Count;
            for (int i = 0; i < n; i++)
            {
                Vector3 p = transform.InverseTransformPoint(s.lip[i]);
                Vector3 d = transform.InverseTransformDirection(s.dir[i]);
                Vector3 tan = Vector3.Cross(Vector3.up, d);
                float tEnd = Mathf.Sqrt(2f * (p.y + 0.35f) / G);
                float pleat = (float)(rng.NextDouble() - 0.5) * 0.3f;   // pliegues: columnas que se adelantan o atrasan
                float rnd = (float)rng.NextDouble();
                float edge = Mathf.Clamp01(1f - Mathf.Min(s.arc[i], s.length - s.arc[i]) / 0.9f);
                for (int k = 0; k < cols; k++)
                {
                    float t = k == 0 ? -Approach / v0 : k == 1 ? -Approach * 0.45f / v0 : tEnd * (k - 2) / Rows;
                    float prog = t <= 0f ? 0f : t / tEnd;
                    Vector3 pos = p + d * (v0 * t);
                    if (t > 0f) pos.y -= 0.5f * G * t * t;
                    pos += d * (pleat * (0.25f + prog)) + tan * ((s.arc[i] - s.length * 0.5f) * 0.07f * prog);
                    V.Add(pos);
                    C.Add(new Color(prog, edge, rnd, 0f));
                    U.Add(new Vector2(s.arc[i], t));
                }
            }
            for (int i = 0; i < n - 1; i++)
                for (int k = 0; k < cols - 1; k++)
                {
                    int a = baseIndex + i * cols + k, b = a + cols;
                    T.Add(a); T.Add(b); T.Add(a + 1);
                    T.Add(a + 1); T.Add(b); T.Add(b + 1);
                }
        }

        /// <summary>Tiras sueltas 0.6 m delante de la lámina (dan profundidad y se ven caer separadas): de 0.6 a
        /// 1.5 m de ancho con huecos, arrancan bajo el rulo del labio.</summary>
        void AddStrips(Sheet s, System.Random rng, List<Vector3> V, List<Color> C, List<Vector2> U, List<int> T)
        {
            const int Rows = 14;
            float a = 0.15f + (float)rng.NextDouble() * 0.5f;
            while (a < s.length - 0.4f)
            {
                float a1 = Mathf.Min(a + 0.6f + (float)rng.NextDouble() * 0.9f, s.length - 0.1f);
                int baseIndex = V.Count;
                float rnd = (float)rng.NextDouble();
                float t0 = 0.2f + (float)rng.NextDouble() * 0.15f;
                for (int c = 0; c < 3; c++)
                {
                    float arc = Mathf.Lerp(a, a1, c * 0.5f);
                    PointAt(s, arc, out Vector3 pw, out Vector3 dw);
                    Vector3 p = transform.InverseTransformPoint(pw);
                    Vector3 d = transform.InverseTransformDirection(dw);
                    float tEnd = Mathf.Sqrt(2f * (p.y + 0.35f) / G);
                    for (int k = 0; k <= Rows; k++)
                    {
                        float t = Mathf.Lerp(t0, tEnd, k / (float)Rows);
                        Vector3 pos = p + d * (v0 * t + 0.6f);
                        pos.y -= 0.5f * G * t * t;
                        V.Add(pos);
                        C.Add(new Color(t / tEnd, c == 1 ? 0f : 1f, rnd, 1f));
                        U.Add(new Vector2(arc + 13.7f, t));
                    }
                }
                for (int c = 0; c < 2; c++)
                    for (int k = 0; k < Rows; k++)
                    {
                        int i0 = baseIndex + c * (Rows + 1) + k, i1 = i0 + Rows + 1;
                        T.Add(i0); T.Add(i1); T.Add(i0 + 1);
                        T.Add(i0 + 1); T.Add(i1); T.Add(i1 + 1);
                    }
                a = a1 + 0.35f + (float)rng.NextDouble() * 0.75f;
            }
        }

        static void PointAt(Sheet s, float arc, out Vector3 p, out Vector3 d)
        {
            int n = s.lip.Length;
            for (int i = 1; i < n; i++)
            {
                if (arc <= s.arc[i] || i == n - 1)
                {
                    float k = Mathf.InverseLerp(s.arc[i - 1], s.arc[i], arc);
                    p = Vector3.Lerp(s.lip[i - 1], s.lip[i], k);
                    d = Vector3.Slerp(s.dir[i - 1], s.dir[i], k);
                    return;
                }
            }
            p = s.lip[0]; d = s.dir[0];
        }

        /// <summary>Si el shader no compila: lámina transparente sin luz con vetas que corren (textura generada).</summary>
        Material FallbackCurtain()
        {
            var m = FXMaterials.MakeUnlitTransparent("KohanFallsCurtainFallback", new Color(0.8f, 0.9f, 0.95f, 0.85f), false);
            const int W = 32, H = 64;
            var tex = new Texture2D(W, H, TextureFormat.RGBA32, false) { name = "FallsStreaks", wrapMode = TextureWrapMode.Repeat, filterMode = FilterMode.Point };
            var rng = new System.Random(3);
            var px = new Color32[W * H];
            for (int x = 0; x < W; x++)
            {
                float ph = (float)rng.NextDouble() * H;
                for (int y = 0; y < H; y++)
                {
                    float v = Mathf.Sin((y + ph) / H * Mathf.PI * 2f * 2f) * 0.5f + 0.5f;
                    px[y * W + x] = v > 0.55f ? new Color32(232, 244, 246, 255) : new Color32(63, 127, 143, 220);
                }
            }
            tex.SetPixels32(px); tex.Apply(false, true);
            m.SetTexture(IdMainTex, tex);
            m.mainTextureScale = new Vector2(0.6f, 0.8f);
            return m;
        }

        // ------------------------------------------------------------------ pozo y cintas
        /// <summary>Banda de espuma pegada a la línea de caída: de 2.6 m detrás (contra la roca) a 8.2 m hacia la arena
        /// (ahí ya está bajo la plataforma). uv.x = metros desde la caída (más lejos donde no cae agua, así el hervor
        /// queda bajo las cortinas y entre ellas solo pasan los anillos); uv.y = metros a lo largo.</summary>
        void BuildPool(FallsData d)
        {
            int n = plungeLine.Length;
            if (n < 2) return;
            float[] offs = { -2.6f, -1.2f, 0f, 0.9f, 1.9f, 3.1f, 4.5f, 6.2f, 8.2f };
            var V = new List<Vector3>(); var U = new List<Vector2>(); var C = new List<Color>(); var T = new List<int>();
            Vector3 c = transform.TransformPoint(V3(d.center, 0));
            float arc = 0f;
            for (int i = 0; i < n; i++)
            {
                if (i > 0) arc += Vector3.Distance(plungeLine[i], plungeLine[i - 1]);
                // peso de cortina suavizado a lo largo (los anillos se tuercen en vez de cortarse)
                float w = 0f, ws = 0f;
                for (int j = -2; j <= 2; j++) { int q = Mathf.Clamp(i + j, 0, n - 1); float k = 3 - Mathf.Abs(j); w += plungeW[q] * k; ws += k; }
                w /= ws;
                Vector3 inward = Flat(c - plungeLine[i]);
                float endFade = Mathf.Clamp01(Mathf.Min(i, n - 1 - i) / 2.5f);
                foreach (float o in offs)
                {
                    Vector3 p = plungeLine[i] + inward * o;
                    p.y = WaterY + 0.06f;
                    V.Add(transform.InverseTransformPoint(p));
                    U.Add(new Vector2(o + (1f - w) * 2.2f, arc));
                    C.Add(new Color(1f, 1f, 1f, endFade));
                }
            }
            int m = offs.Length;
            for (int i = 0; i < n - 1; i++)
                for (int k = 0; k < m - 1; k++)
                {
                    int a = i * m + k, b = a + m;
                    // la línea va de oeste a este con el centro al sur: este orden deja las caras mirando arriba
                    T.Add(a); T.Add(a + 1); T.Add(b);
                    T.Add(a + 1); T.Add(b + 1); T.Add(b);
                }
            poolMat = FoamMaterial("KohanFallsPool", 0f);
            if (poolMat == null) return;
            var mesh = MakeMesh("KohanFallsPool", V, U, C, T);
            FixUpward(mesh);
            int r = 0;
            for (int i = 0; d.rocks != null && i + 3 < d.rocks.Length && r < 4; i += 4, r++)
            {
                Vector3 rp = transform.TransformPoint(new Vector3(d.rocks[i], d.rocks[i + 1], d.rocks[i + 2]));
                poolMat.SetVector("_Rock" + r, new Vector4(rp.x, rp.y, rp.z, d.rocks[i + 3]));
            }
            AddRenderer("Pool", mesh, poolMat);
        }

        void BuildRibbons(FallsData d)
        {
            if (d.ribbons == null || d.ribbons.Length == 0) return;
            ribbonMat = FoamMaterial("KohanFallsRibbons", 2f);
            if (ribbonMat == null) return;
            ribbonMat.SetFloat("_Alpha", 0.4f);
            float half = (d.ribbonWidth > 0f ? d.ribbonWidth : 3f) * 0.5f;
            var V = new List<Vector3>(); var U = new List<Vector2>(); var C = new List<Color>(); var T = new List<int>();
            foreach (var rb in d.ribbons)
            {
                int n = rb.pts != null ? rb.pts.Length / 2 : 0;
                if (n < 2) continue;
                var pts = new Vector3[n];
                for (int i = 0; i < n; i++) pts[i] = transform.TransformPoint(new Vector3(rb.pts[i * 2], 0f, rb.pts[i * 2 + 1]));
                // subdividir cada tramo cada ~1.5 m para que la cinta siga las olas
                var line = new List<Vector3>();
                for (int i = 0; i < n - 1; i++)
                {
                    int sub = Mathf.Max(1, Mathf.CeilToInt(Vector3.Distance(pts[i], pts[i + 1]) / 1.5f));
                    for (int k = 0; k < sub; k++) line.Add(CatmullRom(pts, i, k / (float)sub));
                }
                line.Add(pts[n - 1]);
                float total = 0f;
                for (int i = 1; i < line.Count; i++) total += Vector3.Distance(line[i], line[i - 1]);
                int b0 = V.Count;
                float along = 0f;
                for (int i = 0; i < line.Count; i++)
                {
                    if (i > 0) along += Vector3.Distance(line[i], line[i - 1]);
                    Vector3 f = Flat(line[Mathf.Min(i + 1, line.Count - 1)] - line[Mathf.Max(i - 1, 0)]);
                    Vector3 side = Vector3.Cross(Vector3.up, f) * half;
                    float fade = Mathf.Clamp01(along / 2f) * Mathf.Clamp01((total - along) / 6f);
                    for (int sgn = -1; sgn <= 1; sgn += 2)
                    {
                        Vector3 p = line[i] + side * sgn;
                        p.y = WaterY + 0.07f;
                        V.Add(transform.InverseTransformPoint(p));
                        U.Add(new Vector2(sgn < 0 ? 0f : 1f, along));
                        C.Add(new Color(1f, 1f, 1f, fade));
                    }
                }
                for (int i = 0; i < line.Count - 1; i++)
                {
                    int a = b0 + i * 2;
                    T.Add(a); T.Add(a + 2); T.Add(a + 1);
                    T.Add(a + 1); T.Add(a + 2); T.Add(a + 3);
                }
            }
            if (T.Count == 0) return;
            var mesh = MakeMesh("KohanFallsRibbons", V, U, C, T);
            FixUpward(mesh);
            AddRenderer("Ribbons", mesh, ribbonMat);
        }

        static Vector3 CatmullRom(Vector3[] p, int i, float t)
        {
            Vector3 p0 = p[Mathf.Max(i - 1, 0)], p1 = p[i], p2 = p[Mathf.Min(i + 1, p.Length - 1)], p3 = p[Mathf.Min(i + 2, p.Length - 1)];
            float t2 = t * t, t3 = t2 * t;
            return 0.5f * (2f * p1 + (-p0 + p2) * t + (2f * p0 - 5f * p1 + 4f * p2 - p3) * t2 + (-p0 + 3f * p1 - 3f * p2 + p3) * t3);
        }

        Material FoamMaterial(string name, float mode)
        {
            var sh = Resources.Load<Shader>("Shaders/NindoFoamWater");
            if (sh == null || !sh.isSupported) return null;     // sin espuma: queda el lago de siempre
            var m = new Material(sh) { name = name };
            m.SetFloat("_Mode", mode);
            // las olas tienen que ser las del lago (mismo criterio que FloatingBob): sin agua animada el lago es
            // plano y la espuma no puede subir y bajar 26 cm sobre él
            var c = Game.Content;
            var water = c != null ? c.waterAnimatedMaterial : null;
            if (c == null || !c.useAnimatedWater || water == null || water.shader == null || !water.shader.isSupported)
                m.SetFloat("_WaveHeight", 0f);
            else
            {
                if (water.HasProperty("_WaveHeight")) m.SetFloat("_WaveHeight", water.GetFloat("_WaveHeight"));
                if (water.HasProperty("_WaveSpeed")) m.SetFloat("_WaveSpeed", water.GetFloat("_WaveSpeed"));
            }
            materials.Add(m);
            return m;
        }

        Mesh MakeMesh(string name, List<Vector3> V, List<Vector2> U, List<Color> C, List<int> T)
        {
            var mesh = new Mesh { name = name, indexFormat = V.Count > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
            mesh.SetVertices(V); mesh.SetUVs(0, U); mesh.SetColors(C); mesh.SetTriangles(T, 0);
            mesh.RecalculateBounds();
            // el pozo y las cintas ondulan con las olas en el shader: margen para que no se recorten
            var b = mesh.bounds; b.Expand(new Vector3(0f, 1f, 0f)); mesh.bounds = b;
            meshes.Add(mesh);
            return mesh;
        }

        /// <summary>Da vuelta los triángulos que hayan quedado mirando abajo (el shader del agua usa Cull Back).</summary>
        static void FixUpward(Mesh mesh)
        {
            var v = mesh.vertices; var t = mesh.triangles;
            for (int i = 0; i < t.Length; i += 3)
            {
                Vector3 n = Vector3.Cross(v[t[i + 1]] - v[t[i]], v[t[i + 2]] - v[t[i]]);
                if (n.y < 0f) { int k = t[i + 1]; t[i + 1] = t[i + 2]; t[i + 2] = k; }
            }
            mesh.triangles = t;
        }

        MeshRenderer AddRenderer(string name, Mesh mesh, Material mat)
        {
            var go = new GameObject(name);
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
            return mr;
        }

        // ------------------------------------------------------------------ niebla
        static readonly float[] MistHeights = { 0.6f, 1.6f, 3.0f };
        static readonly float[] MistSteps = { 0.04f, 0.027f, 0.017f };      // x3 escalones = 0.12 / 0.08 / 0.05
        static readonly float[] MistSpeeds = { 1.2f, 1.8f, 2.5f };

        void BuildMist()
        {
            var sh = Resources.Load<Shader>("Shaders/NindoMist");
            if (sh == null || !sh.isSupported) return;
            var quad = new Mesh { name = "MistQuad" };
            quad.vertices = new[] { new Vector3(-0.5f, 0, -0.5f), new Vector3(0.5f, 0, -0.5f), new Vector3(-0.5f, 0, 0.5f), new Vector3(0.5f, 0, 0.5f) };
            quad.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) };
            quad.triangles = new[] { 0, 2, 1, 2, 3, 1 };
            quad.RecalculateBounds();
            meshes.Add(quad);
            Vector3 c = Vector3.Lerp(PlungeCenter, ArenaCenter, 0.35f);
            mistMats = new Material[MistHeights.Length];
            mistSheets = new Transform[MistHeights.Length];
            mistScroll = new Vector2[MistHeights.Length];
            for (int i = 0; i < MistHeights.Length; i++)
            {
                var m = new Material(sh) { name = "KohanMist" + i };
                m.SetColor(IdColor, MistColor);
                m.SetFloat(IdAlphaStep, MistSteps[i]);
                m.SetFloat("_Scale", 0.16f - i * 0.035f);
                m.SetFloat("_Seed", i * 17.3f);
                m.SetVector("_Source", new Vector4(PlungeCenter.x, PlungeCenter.z, 16f, 0f));
                m.renderQueue = (int)RenderQueue.Transparent + i;
                materials.Add(m);
                mistMats[i] = m;
                var mr = AddRenderer("Mist" + i, quad, m);
                mr.transform.SetPositionAndRotation(new Vector3(c.x, WaterY + MistHeights[i], c.z), Quaternion.identity);
                mr.transform.localScale = new Vector3(26f, 1f, 26f);
                mistSheets[i] = mr.transform;
            }
        }

        // ------------------------------------------------------------------ partículas
        void BuildParticles()
        {
            sprayMat = FallsAssets.Spray;
            bool meshFx = sprayMat != null;      // sin el shader de rocío: puntos blandos de siempre

            // 1) grumos que caen del labio (octaedros estirados) + corona de gotas al tocar el agua
            clumps = System("Clumps", meshFx ? sprayMat : FXMaterials.Alpha, 170, meshFx ? FallsAssets.Clump : null, gravity: 1f);
            SizeOverLife(clumps, 0.7f, 1.35f);
            Fade(clumps, 1f, 0.85f, 1f);
            crowns = System("ImpactCrowns", FXMaterials.Alpha, 260, null, clumps.transform);
            {
                var m = crowns.main;
                m.loop = false; m.duration = 0.1f; m.playOnAwake = false;
                m.startLifetime = new ParticleSystem.MinMaxCurve(0.8f, 1.2f);
                m.startSpeed = new ParticleSystem.MinMaxCurve(5f, 9f);
                m.startSize = new ParticleSystem.MinMaxCurve(0.12f, 0.25f);
                m.startColor = new Color(0.86f, 0.94f, 1f, 0.85f);
                m.gravityModifier = 1f;
                var em = crowns.emission; em.enabled = true; em.rateOverTime = 0f;
                em.SetBursts(new[] { new ParticleSystem.Burst(0f, 3, 5) });
                var sh = crowns.shape; sh.enabled = true; sh.shapeType = ParticleSystemShapeType.Cone; sh.angle = 35f; sh.radius = 0.25f;
                sh.rotation = new Vector3(-90f, 0f, 0f);
                Stretch(crowns, 0.04f, 1.4f);
                Fade(crowns, 0.9f, 0.9f, 0f);
                var sub = clumps.subEmitters; sub.enabled = true;
                sub.AddSubEmitter(crowns, ParticleSystemSubEmitterType.Death, ParticleSystemSubEmitterProperties.InheritNothing);
            }
            // 2) hervor del pozo: chorritos facetados que saltan y se achican al caer. Antes crecían (x1.4) y
            //    vivían más de un segundo casi quietos arriba del pozo: blancos, redondos y grandes se leían como
            //    montones de nieve. El agua se lee por el movimiento: rápidos, estirados hacia arriba y efímeros
            boil = System("PlungeBoil", meshFx ? sprayMat : FXMaterials.Alpha, 120, meshFx ? FallsAssets.Ico : null, gravity: 1.2f);
            SizeOverLife(boil, 1f, 0.2f);
            Fade(boil, 1f, 0.75f, 0f);
            // 3) nube de rocío: la banda blanca que asoma detrás de la baranda norte desde el juego, pegada a la
            //    caída (con bloques de 5 m sobre la plataforma tapaba la pelea). Eran icosaedros facetados opacos y
            //    tramados: desde la cámara de juego se leían como piedras nevadas arriba de la baranda, por más chicos
            //    que fueran. Ahora es vapor blando que sube rápido, se abre y se deshace, con el turbulento del pozo
            cloud = System("SprayCloud", FXMaterials.Alpha, 80, null);
            {
                var nz = cloud.noise; nz.enabled = true; nz.strength = 1.1f; nz.frequency = 0.35f; nz.scrollSpeed = 0.4f; nz.quality = ParticleSystemNoiseQuality.Low;
                var rot = cloud.rotationOverLifetime; rot.enabled = true; rot.z = new ParticleSystem.MinMaxCurve(-0.6f, 0.6f);
                SizeOverLife(cloud, 0.5f, 1.7f);
                Fade(cloud, 0.34f, 0.24f, 0f, fadeIn: true);
            }
            // 4) cola de gallo: gotas estiradas que salen disparadas del pie, la mayoría hacia la arena
            rooster = System("RoosterTail", FXMaterials.Alpha, 220, null, gravity: 0.9f);
            Stretch(rooster, 0.035f, 1.3f);
            Fade(rooster, 0.85f, 0.8f, 0f);
            glints = System("MoonGlints", FXMaterials.Additive, 24, null, gravity: 0.9f);
            Stretch(glints, 0.03f, 1.2f);
            Fade(glints, 1f, 1f, 0f);
            // 5) niebla que rueda sobre el pozo (manchas blandas grandes)
            rolling = System("RollingMist", FXMaterials.Alpha, 30, null);
            {
                var nz = rolling.noise; nz.enabled = true; nz.strength = 0.8f; nz.frequency = 0.12f; nz.scrollSpeed = 0.15f; nz.quality = ParticleSystemNoiseQuality.Low;
                SizeOverLife(rolling, 0.7f, 1.5f);
                Fade(rolling, 0.12f, 0.1f, 0f, fadeIn: true);
            }
            // 5b) columnas de niebla: manchas blandas enormes que suben 10-18 m pegadas a la roca. Desde el juego
            //     quedan casi todas arriba del cuadro; en las tomas del jefe dan la escala de la caída
            columns = System("MistColumns", FXMaterials.Alpha, 32, null);
            {
                var nz = columns.noise; nz.enabled = true; nz.strength = 0.6f; nz.frequency = 0.08f; nz.scrollSpeed = 0.1f; nz.quality = ParticleSystemNoiseQuality.Low;
                SizeOverLife(columns, 0.6f, 1.6f);
                Fade(columns, 0.09f, 0.06f, 0f, fadeIn: true);
            }
            // 6) llovizna con viento sobre la plataforma (y sus destellos de luna)
            drizzle = System("Drizzle", FXMaterials.Alpha, 300, null);
            ConfigureDrizzle(drizzle, 110f, new Color(0.78f, 0.87f, 0.95f, 0.55f), 0.03f);
            drizzleGlints = System("DrizzleGlints", FXMaterials.Additive, 50, null);
            ConfigureDrizzle(drizzleGlints, 18f, new Color(0.81f, 0.9f, 1f, 0.9f), 0.04f);
            drizzles = new[] { drizzle, drizzleGlints };
        }

        ParticleSystem System(string name, Material mat, int max, Mesh mesh, Transform parent = null, float gravity = 0f)
        {
            var ps = FXFactory.NewSystem(name, parent != null ? parent : transform);
            var m = ps.main;
            m.loop = true; m.duration = 10f; m.playOnAwake = true;
            m.maxParticles = max;
            m.gravityModifier = gravity;
            m.simulationSpace = ParticleSystemSimulationSpace.World;
            m.startSize3D = mesh != null;
            m.startRotation3D = mesh != null;
            var em = ps.emission; em.enabled = false;           // se emite a mano (Emit) desde los labios
            var sh = ps.shape; sh.enabled = false;
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.sharedMaterial = mat;
            if (mesh != null)
            {
                r.renderMode = ParticleSystemRenderMode.Mesh;
                r.mesh = mesh;
                r.alignment = ParticleSystemRenderSpace.World;
            }
            if (parent == null) systems.Add(ps);
            return ps;
        }

        static void SizeOverLife(ParticleSystem ps, float a, float b)
        {
            var s = ps.sizeOverLifetime; s.enabled = true;
            s.size = new ParticleSystem.MinMaxCurve(1f, new AnimationCurve(new Keyframe(0f, a), new Keyframe(1f, b)));
        }

        static void Fade(ParticleSystem ps, float a0, float aMid, float a1, bool fadeIn = false)
        {
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      fadeIn ? new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(a0, 0.2f), new GradientAlphaKey(aMid, 0.6f), new GradientAlphaKey(a1, 1f) }
                             : new[] { new GradientAlphaKey(a0, 0f), new GradientAlphaKey(aMid, 0.55f), new GradientAlphaKey(a1, 1f) });
            col.color = new ParticleSystem.MinMaxGradient(g);
        }

        static void Stretch(ParticleSystem ps, float velocityScale, float lengthScale)
        {
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.Stretch;
            r.velocityScale = velocityScale;
            r.lengthScale = lengthScale;
        }

        void ConfigureDrizzle(ParticleSystem ps, float rate, Color c, float size)
        {
            var m = ps.main;
            // ~7.5 m de caída: mueren a la altura de la plataforma (sobre el agua siguen apenas 1 m)
            m.startLifetime = new ParticleSystem.MinMaxCurve(1.05f, 1.25f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(5f, 7f);
            m.startSize = new ParticleSystem.MinMaxCurve(size * 0.8f, size * 1.2f);
            m.startColor = c;
            m.gravityModifier = 0.3f;
            var em = ps.emission; em.enabled = true; em.rateOverTime = rate;
            var sh = ps.shape; sh.enabled = true; sh.shapeType = ParticleSystemShapeType.Box;
            // la caja dispara en su +Z: girada 90° en X tira hacia abajo (y su Y local pasa a ser el Z del mundo)
            sh.scale = new Vector3(24f, 16f, 0.5f);
            sh.rotation = new Vector3(90f, 0f, 0f);
            ps.transform.SetPositionAndRotation(Vector3.Lerp(ArenaCenter, PlungeCenter, 0.3f) + Vector3.up * (DeckY - ArenaCenter.y + 7.5f), Quaternion.identity);
            var vel = ps.velocityOverLifetime; vel.enabled = true; vel.space = ParticleSystemSimulationSpace.World;
            var nz = ps.noise; nz.enabled = true; nz.strength = 1.5f; nz.frequency = 0.5f; nz.quality = ParticleSystemNoiseQuality.Low;
            Stretch(ps, 0.03f, 3f);
            Fade(ps, 1f, 1f, 0.6f);
        }

        // ------------------------------------------------------------------ arcoíris de luna, luz y sonido
        void BuildMoonbow()
        {
            // en el rocío del pie, hacia el punto opuesto a la luna (un poco al oeste del eje): 7 franjas pastel
            // desaturadas con el centro blanco, aditivo y muy tenue
            Color[] bands = { new Color(1f, 0.72f, 0.72f), new Color(1f, 0.86f, 0.68f), new Color(1f, 1f, 0.74f), new Color(0.74f, 1f, 0.8f),
                              new Color(0.7f, 0.86f, 1f), new Color(0.76f, 0.74f, 1f), new Color(0.9f, 0.76f, 1f), new Color(1f, 1f, 1f) };
            const float R = 14f, W = 0.32f;
            Vector3 right = Vector3.Cross(Vector3.up, windDir);          // perpendicular al eje de la cascada
            Vector3 center = PlungeCenter + windDir * 1.5f - right * 3f + Vector3.down * 5f;
            var V = new List<Vector3>(); var C = new List<Color>(); var U = new List<Vector2>(); var T = new List<int>();
            const int Seg = 40;
            for (int b = 0; b < bands.Length; b++)
            {
                float r0 = R - b * W, r1 = r0 - W;
                int i0 = V.Count;
                for (int k = 0; k <= Seg; k++)
                {
                    float a = Mathf.Lerp(20f, 160f, k / (float)Seg) * Mathf.Deg2Rad;
                    Vector3 dir = right * Mathf.Cos(a) + Vector3.up * Mathf.Sin(a);
                    Vector3 pa = center + dir * r0, pb = center + dir * r1;
                    // se apaga en las puntas y bajo el agua
                    float fade = Mathf.Clamp01(Mathf.Sin((k / (float)Seg) * Mathf.PI) * 1.6f) * Mathf.Clamp01((pa.y - WaterY - 0.5f) / 3f);
                    float alpha = (b == bands.Length - 1 ? 0.06f : 0.1f) * fade;
                    Color c = bands[b]; c.a = alpha;
                    V.Add(transform.InverseTransformPoint(pa)); V.Add(transform.InverseTransformPoint(pb));
                    C.Add(c); C.Add(c);
                    U.Add(new Vector2(0.5f, 0.5f)); U.Add(new Vector2(0.5f, 0.5f));
                }
                for (int k = 0; k < Seg; k++)
                {
                    int a = i0 + k * 2;
                    T.Add(a); T.Add(a + 2); T.Add(a + 1);
                    T.Add(a + 1); T.Add(a + 2); T.Add(a + 3);
                }
            }
            var mesh = MakeMesh("KohanMoonbow", V, U, C, T);
            moonbowMat = FXMaterials.MakeParticle("KohanMoonbow", true);
            materials.Add(moonbowMat);
            AddRenderer("Moonbow", mesh, moonbowMat);
        }

        /// <summary>Luz fría desde el norte: un foco alto delante de la caída que apunta a la plataforma. Un punto de
        /// luz cerca del pozo daba ~1 % en el centro de la arena (caída 1/d² de URP) o, subido, quemaba la baranda
        /// norte y la cortina; el foco alto aplana la caída (centro ~0.17, baranda ~0.3) y deja la cortina, que
        /// queda detrás del cono, sin manchas. Ilumina por detrás a Kaito y al koi vistos desde la cámara, el
        /// rocío y el pie de las cortinas.</summary>
        void BuildLight()
        {
            var go = new GameObject("FallsFill");
            go.transform.SetParent(transform, false);
            Vector3 pos = PlungeCenter + windDir * 3f + Vector3.up * 14f;
            Vector3 aim = new Vector3(ArenaCenter.x, DeckY + 1f, ArenaCenter.z);
            go.transform.SetPositionAndRotation(pos, Quaternion.LookRotation(aim - pos, Vector3.up));
            fill = go.AddComponent<Light>();
            fill.type = LightType.Spot;
            // cono pleno hasta 50° del eje: la plataforma entera; el rocío del pie (~56°) recibe la mitad y la
            // cortina a media altura (~67°) casi nada
            fill.spotAngle = 140f;
            fill.innerSpotAngle = 100f;
            fill.color = FillColor;
            fill.range = 32f;
            fill.intensity = FillIntensity;
            fill.shadows = LightShadows.None;
        }

        void BuildAudio()
        {
            var c = Game.LoadContent();
            roarEntry = c.Sfx("falls_roar");
            hissEntry = c.Sfx("falls_spray");
            roar = Loop("FallsRoar", roarEntry, 18f, RoarMax, AudioRolloffMode.Custom);
            if (roar != null)
                // como la logarítmica (pleno hasta 18 m, la mitad hacia los 40) pero llega a 0 en RoarMax: la
                // logarítmica de Unity se queda en 18/140 (-18 dB) más allá del máximo y la cascada se oía en todo el mapa
                roar.SetCustomCurve(AudioSourceCurveType.CustomRolloff, new AnimationCurve(
                    new Keyframe(0f, 1f), new Keyframe(18f / RoarMax, 1f), new Keyframe(0.4f, 0.35f), new Keyframe(1f, 0f)));
            hiss = Loop("FallsSpray", hissEntry, 4f, 26f, AudioRolloffMode.Linear);
        }

        AudioSource Loop(string name, NindoContent.AudioEntry e, float min, float max, AudioRolloffMode mode)
        {
            if (e == null || e.clips == null || e.clips.Length == 0 || e.clips[0] == null) return null;
            var go = new GameObject(name);
            go.transform.SetParent(transform, false);
            go.transform.position = PlungeCenter + Vector3.up * 2f;
            var s = go.AddComponent<AudioSource>();
            s.clip = e.clips[0];
            s.loop = true; s.playOnAwake = false; s.spatialBlend = 1f; s.dopplerLevel = 0f;
            s.rolloffMode = mode; s.minDistance = min; s.maxDistance = max;
            s.priority = 40;
            s.volume = 0f;
            s.time = UnityEngine.Random.Range(0f, s.clip.length * 0.9f);
            s.Play();
            return s;
        }

        // ================================================================== frame
        void ApplyQuality()
        {
            lowQuality = QualitySettings.GetQualityLevel() <= 1;
            if (drizzle != null) { var e = drizzle.emission; e.enabled = !lowQuality; }
            if (drizzleGlints != null) { var e = drizzleGlints.emission; e.enabled = !lowQuality; }
            if (mistSheets != null)
                for (int i = 1; i < mistSheets.Length; i++) mistSheets[i].gameObject.SetActive(!lowQuality);
        }

        void Update()
        {
            float dt = Time.deltaTime;
            // LOD por Kaito (o por la cámara mientras él no existe, p. ej. al armar el mundo)
            Transform viewer = Game.Player != null ? Game.Player.transform : (Game.Camera != null ? Game.Camera.transform : null);
            Vector3 player = viewer != null ? viewer.position : PlungeCenter + Vector3.forward * 1e4f;
            bool near = (player - PlungeCenter).sqrMagnitude < LodDistance * LodDistance;
            if (near != Active) SetActive(near);
            if ((qualityTimer -= Time.unscaledDeltaTime) <= 0f) { qualityTimer = 2f; ApplyQuality(); }

            // caudal: se suaviza hacia el objetivo; el golpe de agua sube rápido y baja en 1 s
            intensity = Mathf.MoveTowards(intensity, intensityTarget, dt * 0.5f);
            float k = intensity * SurgeFactor();
            corrupt = Mathf.MoveTowards(corrupt, corruptTarget, dt * 0.6f);
            UpdateGust(dt, k);
            UpdateMaterials(k, dt);
            UpdateAudio(k);
            UpdateAudioPause(player);
            if (!Active) return;

            Shader.SetGlobalVector(IdPlayer, new Vector4(player.x, player.y, player.z, 1f));
            Transform boss = BossFocus != null ? BossFocus : (Game.Combat != null && Game.Combat.ActiveBoss != null ? Game.Combat.ActiveBoss.transform : null);
            Shader.SetGlobalVector(IdBoss, boss != null ? new Vector4(boss.position.x, boss.position.y, boss.position.z, 1f) : Vector4.zero);
            if (fill != null)
                fill.intensity = FillIntensity * (0.9f + 0.1f * k) * (0.9f + 0.2f * Mathf.PerlinNoise(Time.time * 2.5f, 0.37f));
            Emit(dt, k);
        }

        float SurgeFactor()
        {
            if (Time.time >= surgeEnd + 1f) return 1f;
            float rise = Mathf.Clamp01((Time.time - surgeStart) / 0.3f);
            float fall = Time.time > surgeEnd ? 1f - Mathf.Clamp01(Time.time - surgeEnd) : 1f;
            return 1f + (surgeMult - 1f) * rise * fall;
        }

        void SetActive(bool on)
        {
            Active = on;
            foreach (var ps in systems)
            {
                if (on) ps.Play(true);
                else ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            }
            if (fill != null) fill.enabled = on;
            if (!on) Shader.SetGlobalVector(IdBoss, Vector4.zero);
        }

        /// <summary>Ráfagas: cada 7-11 s (4-7 s en la crecida) durante 1.6 s la niebla corre el doble y gira hasta 25°,
        /// la llovizna se duplica, una sábana de gotas cruza la plataforma y las cortinas se mecen más, con un "fuuu".</summary>
        void UpdateGust(float dt, float k)
        {
            gustTimer -= dt;
            if (gustTimer <= 0f)
            {
                bool flood = k > 1.2f;
                gustTimer = flood ? UnityEngine.Random.Range(4f, 7f) : UnityEngine.Random.Range(7f, 11f);
                gustDur = 1.6f;
                gustAngle = UnityEngine.Random.Range(-25f, 25f);
                if (Active && Game.Player != null)
                {
                    // el "fuuu" sale de la baranda norte y solo en la plataforma o cerca (en los muelles, a 100 m,
                    // sonaba al lado de Kaito); en combate baja como los loops, para no tapar los avisos
                    float near = 1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(25f, 45f, Vector3.Distance(Game.Player.transform.position, ArenaCenter)));
                    if (near > 0f)
                    {
                        bool combat = Game.Combat != null && Game.Combat.InCombat;
                        Game.Audio?.Play("falls_gust", Vector3.Lerp(PlungeCenter, ArenaCenter, 0.25f) + Vector3.up * 3f, 0.8f * near * (combat ? 0.55f : 1f));
                    }
                    EmitGustSheet();
                }
            }
            gustDur -= dt;
            float target = gustDur > 0f ? Mathf.Sin(Mathf.Clamp01(1f - gustDur / 1.6f) * Mathf.PI) : 0f;
            gust = Mathf.MoveTowards(gust, target, dt * 3f);
            Vector3 w = Quaternion.AngleAxis(gustAngle * gust, Vector3.up) * windDir;
            Shader.SetGlobalVector(IdWind, new Vector4(w.x * (0.8f + 0.2f * k), 0f, w.z * (0.8f + 0.2f * k), gust));
            if (mistMats != null)
                for (int i = 0; i < mistMats.Length; i++)
                {
                    mistScroll[i] += new Vector2(w.x, w.z) * (MistSpeeds[i] * (1f + gust) * (0.8f + 0.2f * k) * dt);
                    mistMats[i].SetVector(IdScroll, new Vector4(mistScroll[i].x, mistScroll[i].y, 0f, 0f));
                    mistMats[i].SetFloat(IdAlphaStep, MistSteps[i] * (0.85f + 0.15f * k));
                }
            if (drizzle != null && Active)
            {
                float speed = 2f * (1f + gust) * (0.8f + 0.2f * k);
                foreach (var ps in drizzles)
                {
                    var vel = ps.velocityOverLifetime;
                    vel.x = new ParticleSystem.MinMaxCurve(w.x * speed);
                    vel.z = new ParticleSystem.MinMaxCurve(w.z * speed);
                    vel.y = new ParticleSystem.MinMaxCurve(0f);
                    var em = ps.emission;
                    em.rateMultiplier = (1f + gust) * (0.8f + 0.2f * k) * (lowQuality ? 0.5f : 1f);
                }
            }
        }

        void UpdateMaterials(float k, float dt)
        {
            // la fase se acumula acá: con _Time.y * caudal en el shader cada cambio de caudal saltaba la fase
            // Time.time * delta y las vetas corrían cientos de veces más rápido, o hacia arriba, justo en el cambio de fase
            flowPhase += dt * k;
            if (curtainMat != null)
            {
                if (curtainMat.HasProperty(IdFlowPhase))
                {
                    curtainMat.SetFloat(IdFlowPhase, flowPhase);
                    curtainMat.SetFloat(IdIntensity, k);
                    curtainMat.SetFloat(IdTurb, 1f + (k - 1f) * 0.8f);
                    curtainMat.SetFloat(IdCorrupt, corrupt);
                }
                else curtainMat.mainTextureOffset += new Vector2(0f, dt * 0.9f * k);   // respaldo sin shader
            }
            if (poolMat != null) { poolMat.SetFloat(IdPoolFlow, k); poolMat.SetFloat(IdFlowPhase, flowPhase); }
            if (ribbonMat != null) { ribbonMat.SetFloat(IdPoolFlow, k); ribbonMat.SetFloat(IdFlowPhase, flowPhase); }
            if (moonbowMat != null)
            {
                // es aditivo: el refuerzo va por el RGB (por el alfa se saturaba en 1 y x2 era apenas +14 %)
                float b = MoonbowBoost;
                moonbowMat.SetColor(IdBaseColor, new Color(b, b, b, 0.75f + 0.25f * Mathf.PerlinNoise(Time.time * 0.3f, 1.7f)));
            }
        }

        void UpdateAudio(float k)
        {
            if ((volumeTimer -= Time.unscaledDeltaTime) <= 0f)
            {
                volumeTimer = 0.5f;
                // en combate se baja ~5 dB: los avisos de los golpes tienen que oírse por encima del agua
                bool combat = Game.Combat != null && Game.Combat.InCombat;
                volumeTarget = Settings.MasterVolume * Settings.SfxVolume * (combat ? 0.55f : 1f) * (0.85f + 0.15f * k);
            }
            float pitch = Game.IsPaused ? 1f : Mathf.Lerp(0.55f, 1f, Game.Time != null ? Mathf.Clamp01(Game.Time.SlowMoScale) : 1f);
            if (roar != null)
            {
                roar.volume = Mathf.MoveTowards(roar.volume, volumeTarget * roarEntry.volume, Time.unscaledDeltaTime * 0.6f);
                roar.pitch = pitch * (0.97f + 0.03f * k);
            }
            if (hiss != null)
            {
                hiss.volume = Mathf.MoveTowards(hiss.volume, volumeTarget * hissEntry.volume * (0.85f + 0.3f * gust), Time.unscaledDeltaTime * 0.8f);
                hiss.pitch = pitch;
            }
        }

        /// <summary>Lejos de la cascada los loops se pausan (no ocupan voces); la curva ya los dejó en 0 antes.
        /// Margen de 35 m: el oyente es la cámara, que va hasta ~30 m detrás de Kaito.</summary>
        void UpdateAudioPause(Vector3 player)
        {
            bool far = (player - PlungeCenter).sqrMagnitude > (RoarMax + 35f) * (RoarMax + 35f);
            if (far == audioPaused) return;
            audioPaused = far;
            foreach (var src in new[] { roar, hiss })
            {
                if (src == null) continue;
                if (far) src.Pause(); else src.UnPause();
            }
        }

        // ------------------------------------------------------------------ emisión a mano
        void Emit(float dt, float k)
        {
            float q = lowQuality ? 0.5f : 1f;
            float rate = k * q;
            for (int n = Take(ref aClump, 45f * rate * dt); n > 0; n--) EmitClump();
            for (int n = Take(ref aBoil, 80f * rate * dt); n > 0; n--) EmitBoil();
            for (int n = Take(ref aCloud, 26f * rate * dt); n > 0; n--) EmitCloud();
            for (int n = Take(ref aRooster, 100f * rate * dt); n > 0; n--) EmitRooster(rooster, false);
            for (int n = Take(ref aGlint, 10f * rate * dt); n > 0; n--) EmitRooster(glints, true);
            for (int n = Take(ref aRolling, 6f * q * dt); n > 0; n--) EmitRolling();
            for (int n = Take(ref aColumn, 3.5f * q * dt); n > 0; n--) EmitColumn();
        }

        static int Take(ref float acc, float add)
        {
            acc += add;
            int n = (int)acc;
            acc -= n;
            return Mathf.Min(n, 12);     // un frame largo no descarga una ráfaga entera de golpe
        }

        Sheet PickSheet()
        {
            float r = UnityEngine.Random.value * totalWeight;
            foreach (var s in sheets) { r -= s.weight; if (r <= 0f) return s; }
            return sheets[sheets.Count - 1];
        }

        /// <summary>Punto al azar sobre un labio: posición del labio, dirección del agua, tiempo de caída y pie.</summary>
        void LipSample(out Vector3 lip, out Vector3 dir, out float fall, out Vector3 foot)
        {
            var s = PickSheet();
            float arc = UnityEngine.Random.value * s.length;
            int n = s.lip.Length;
            int i = 1;
            while (i < n - 1 && s.arc[i] < arc) i++;
            float t = Mathf.InverseLerp(s.arc[i - 1], s.arc[i], arc);
            lip = Vector3.Lerp(s.lip[i - 1], s.lip[i], t);
            dir = Vector3.Slerp(s.dir[i - 1], s.dir[i], t);
            fall = Mathf.Lerp(s.fall[i - 1], s.fall[i], t);
            foot = Vector3.Lerp(s.plunge[i - 1], s.plunge[i], t);
        }

        void EmitClump()
        {
            LipSample(out var lip, out var dir, out float fall, out _);
            float side = UnityEngine.Random.Range(-1f, 1f);
            var ep = new ParticleSystem.EmitParams
            {
                position = lip + dir * UnityEngine.Random.Range(0.1f, 0.5f) + Vector3.Cross(Vector3.up, dir) * side * 0.2f,
                velocity = dir * (v0 + UnityEngine.Random.Range(-0.3f, 0.3f)),
                // vive exactamente lo que tarda en caer (sale del labio sin velocidad vertical): muere en el agua y la
                // corona sale de ahí. Un ±2 % acá eran ±1.7 m de altura a 29 m/s: coronas en el aire o bajo el agua
                startLifetime = fall,
                // finos y largos: con 1.8 de alto parecían diamantes de hielo quietos delante de la cortina
                startSize3D = new Vector3(0.75f, 2.6f, 0.75f) * UnityEngine.Random.Range(0.3f, 0.75f),
                rotation3D = new Vector3(0f, UnityEngine.Random.Range(0f, 360f), 0f),
                startColor = Color.white,
            };
            clumps.Emit(ep, 1);
        }

        void EmitBoil()
        {
            LipSample(out _, out var dir, out _, out var foot);
            Vector3 up = Quaternion.AngleAxis(UnityEngine.Random.Range(-15f, 15f), Vector3.Cross(Vector3.up, dir)) * Quaternion.AngleAxis(UnityEngine.Random.Range(-15f, 15f), dir) * Vector3.up;
            float size = UnityEngine.Random.Range(0.3f, 0.85f);
            var ep = new ParticleSystem.EmitParams
            {
                position = foot + dir * UnityEngine.Random.Range(-0.6f, 0.8f) + Vector3.Cross(Vector3.up, dir) * UnityEngine.Random.Range(-0.6f, 0.6f),
                velocity = (up + dir * 0.25f).normalized * UnityEngine.Random.Range(4.5f, 8.5f),
                startLifetime = UnityEngine.Random.Range(0.55f, 0.85f),
                // estirado hacia arriba y apenas inclinado: un chorrito, no una piedra
                startSize3D = new Vector3(size, size * 1.8f, size),
                rotation3D = new Vector3(UnityEngine.Random.Range(-20f, 20f), UnityEngine.Random.Range(0f, 360f), UnityEngine.Random.Range(-20f, 20f)),
                // de blanco a agua del pozo: todo blanco parejo era nieve
                startColor = Color.Lerp(Color.white, WaterTint, UnityEngine.Random.value * 0.75f),
            };
            boil.Emit(ep, 1);
        }

        void EmitCloud()
        {
            LipSample(out _, out var dir, out _, out var foot);
            var ep = new ParticleSystem.EmitParams
            {
                position = foot + dir * UnityEngine.Random.Range(-0.5f, 1f) + Vector3.up * UnityEngine.Random.Range(0.2f, 1f),
                // sube rápido casi derecha (el aire que empuja la caída); el viento del pozo apenas la arrima
                velocity = Vector3.up * UnityEngine.Random.Range(2.6f, 4.6f) + windDir * UnityEngine.Random.Range(0.3f, 0.8f),
                startLifetime = UnityEngine.Random.Range(1.7f, 2.3f),
                startSize = UnityEngine.Random.Range(2.2f, 3.6f),
                rotation = UnityEngine.Random.Range(0f, 360f),
                startColor = Color.Lerp(Color.white, MistColor, UnityEngine.Random.value),
            };
            cloud.Emit(ep, 1);
        }

        void EmitRooster(ParticleSystem ps, bool glint)
        {
            LipSample(out _, out var dir, out _, out var foot);
            // 70 % hacia la arena; el resto, de costado y contra la roca. Alcance <= ~6 m: llega a la baranda norte,
            // no cruza la plataforma (sobre la plataforma ya está la llovizna)
            Vector3 flat = UnityEngine.Random.value < 0.7f ? dir : Quaternion.AngleAxis(UnityEngine.Random.Range(-120f, 120f), Vector3.up) * dir;
            float elev = UnityEngine.Random.Range(25f, 70f) * Mathf.Deg2Rad;
            Vector3 v = (flat * Mathf.Cos(elev) + Vector3.up * Mathf.Sin(elev)) * UnityEngine.Random.Range(4f, 8.5f);
            var ep = new ParticleSystem.EmitParams
            {
                position = foot + Vector3.up * 0.2f + Vector3.Cross(Vector3.up, dir) * UnityEngine.Random.Range(-0.8f, 0.8f),
                velocity = v,
                startLifetime = UnityEngine.Random.Range(0.9f, 1.3f),
                startSize = glint ? UnityEngine.Random.Range(0.08f, 0.14f) : UnityEngine.Random.Range(0.2f, 0.5f),
                startColor = glint ? new Color(0.81f, 0.9f, 1f, 1f) : new Color(0.86f, 0.93f, 1f, 0.8f),
            };
            ps.Emit(ep, 1);
        }

        /// <summary>Punto al azar de la línea de caída donde cae agua (también bajo las cintas laterales).</summary>
        bool PlungeSample(out Vector3 p)
        {
            p = PlungeCenter;
            if (plungeLine == null || plungeLine.Length < 2 || plungeWTotal <= 0f) return false;
            float r = UnityEngine.Random.value * plungeWTotal;
            int i = 0;
            for (; i < plungeLine.Length - 1; i++) { r -= plungeW[i]; if (r <= 0f) break; }
            p = Vector3.Lerp(plungeLine[i], plungeLine[Mathf.Min(i + 1, plungeLine.Length - 1)], UnityEngine.Random.value);
            return true;
        }

        void EmitColumn()
        {
            if (!PlungeSample(out var p)) return;
            columns.Emit(new ParticleSystem.EmitParams
            {
                position = p - windDir * UnityEngine.Random.Range(0f, 1.5f) + Vector3.up * UnityEngine.Random.Range(1f, 3f),
                velocity = Vector3.up * UnityEngine.Random.Range(1.2f, 2.2f) + windDir * 0.3f,
                startLifetime = UnityEngine.Random.Range(7f, 9f),
                startSize = UnityEngine.Random.Range(4f, 6.5f),
                rotation = UnityEngine.Random.Range(0f, 360f),
                startColor = MistColor,
            }, 1);
        }

        /// <summary>Al empezar una ráfaga: una sábana de gotas finas que cruza la plataforma desde la baranda norte.</summary>
        void EmitGustSheet()
        {
            if (lowQuality || drizzle == null) return;
            Vector3 side = Vector3.Cross(Vector3.up, windDir);
            Vector3 start = Vector3.Lerp(PlungeCenter, ArenaCenter, 0.2f);
            for (int i = 0; i < 70; i++)
            {
                var ps = i % 6 == 0 ? drizzleGlints : drizzle;
                ps.Emit(new ParticleSystem.EmitParams
                {
                    position = start + side * UnityEngine.Random.Range(-11f, 11f) + windDir * UnityEngine.Random.Range(-1f, 1f)
                               + Vector3.up * (DeckY - start.y + UnityEngine.Random.Range(0.5f, 4f)),
                    velocity = windDir * UnityEngine.Random.Range(6f, 9f) + Vector3.up * UnityEngine.Random.Range(0.3f, 1.4f),
                    startLifetime = UnityEngine.Random.Range(1.2f, 1.7f),
                    startSize = UnityEngine.Random.Range(0.03f, 0.05f),
                    startColor = new Color(0.8f, 0.89f, 0.97f, 0.7f),
                }, 1);
            }
        }

        void EmitRolling()
        {
            if (!PlungeSample(out var p)) return;
            var ep = new ParticleSystem.EmitParams
            {
                position = p + Vector3.up * UnityEngine.Random.Range(0.4f, 2.2f),
                velocity = windDir * UnityEngine.Random.Range(0.5f, 1.1f) + Vector3.up * 0.2f,
                startLifetime = UnityEngine.Random.Range(4f, 6f),
                startSize = UnityEngine.Random.Range(3f, 6f),
                rotation = UnityEngine.Random.Range(0f, 360f),
                startColor = MistColor,
            };
            rolling.Emit(ep, 1);
        }
    }

    /// <summary>Mallas compartidas de las partículas de agua (facetadas, como el resto del mundo).</summary>
    static class FallsAssets
    {
        static Mesh clump, ico, blob;
        static Material spray, splashSpray;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() { clump = ico = blob = null; spray = splashSpray = null; }

        /// <summary>Octaedro estirado en Y (8 caras): grumo de agua que cae.</summary>
        public static Mesh Clump => clump != null ? clump : (clump = Octahedron());

        /// <summary>Icosaedro (20 caras): hervor y espuma.</summary>
        public static Mesh Ico => ico != null ? ico : (ico = Icosphere("WaterIco", 0, 0f, 1));

        /// <summary>Icosaedro subdividido y deformado (80 caras): nube de rocío.</summary>
        public static Mesh Blob => blob != null ? blob : (blob = Icosphere("WaterBlob", 1, 0.22f, 7));

        /// <summary>Material de rocío (shader Nindo/Spray); null si no compiló.</summary>
        public static Material Spray
        {
            get
            {
                if (spray == null)
                {
                    var sh = Resources.Load<Shader>("Shaders/NindoSpray");
                    if (sh != null && sh.isSupported)
                    {
                        spray = new Material(sh) { name = "NindoSpray" };
                        // la cara en sombra va a azul de agua: con el gris claro de antes los grumos eran hielo
                        spray.SetColor("_Shade", new Color(0.5f, 0.67f, 0.8f));
                    }
                }
                return spray;
            }
        }

        /// <summary>El mismo rocío pero sin despejarse alrededor de Kaito y del jefe: para los salpicones que nacen
        /// del cuerpo del jefe (con el despeje se borraba casi toda la espuma del varado).</summary>
        public static Material SplashSpray
        {
            get
            {
                if (splashSpray == null && Spray != null)
                {
                    splashSpray = new Material(Spray) { name = "NindoSplashSpray" };
                    splashSpray.SetFloat("_ClearAmount", 0f);
                }
                return splashSpray;
            }
        }

        static Mesh Octahedron()
        {
            var v = new[] { new Vector3(0, 0.5f, 0), new Vector3(0.5f, 0, 0), new Vector3(0, 0, 0.5f), new Vector3(-0.5f, 0, 0), new Vector3(0, 0, -0.5f), new Vector3(0, -0.5f, 0) };
            int[] f = { 0, 2, 1, 0, 3, 2, 0, 4, 3, 0, 1, 4, 5, 1, 2, 5, 2, 3, 5, 3, 4, 5, 4, 1 };
            return Flat("WaterClump", v, f);
        }

        static Mesh Icosphere(string name, int subdiv, float jitter, int seed)
        {
            float t = (1f + Mathf.Sqrt(5f)) / 2f;
            var verts = new List<Vector3>
            {
                new Vector3(-1, t, 0), new Vector3(1, t, 0), new Vector3(-1, -t, 0), new Vector3(1, -t, 0),
                new Vector3(0, -1, t), new Vector3(0, 1, t), new Vector3(0, -1, -t), new Vector3(0, 1, -t),
                new Vector3(t, 0, -1), new Vector3(t, 0, 1), new Vector3(-t, 0, -1), new Vector3(-t, 0, 1),
            };
            var faces = new List<int>
            {
                0, 11, 5, 0, 5, 1, 0, 1, 7, 0, 7, 10, 0, 10, 11, 1, 5, 9, 5, 11, 4, 11, 10, 2, 10, 7, 6, 7, 1, 8,
                3, 9, 4, 3, 4, 2, 3, 2, 6, 3, 6, 8, 3, 8, 9, 4, 9, 5, 2, 4, 11, 6, 2, 10, 8, 6, 7, 9, 8, 1,
            };
            for (int s = 0; s < subdiv; s++)
            {
                var mid = new Dictionary<long, int>();
                var nf = new List<int>();
                int Mid(int a, int b)
                {
                    long key = a < b ? ((long)a << 32) | (uint)b : ((long)b << 32) | (uint)a;
                    if (mid.TryGetValue(key, out int i)) return i;
                    verts.Add((verts[a] + verts[b]) * 0.5f);
                    mid[key] = verts.Count - 1;
                    return verts.Count - 1;
                }
                for (int i = 0; i < faces.Count; i += 3)
                {
                    int a = faces[i], b = faces[i + 1], c = faces[i + 2];
                    int ab = Mid(a, b), bc = Mid(b, c), ca = Mid(c, a);
                    nf.AddRange(new[] { a, ab, ca, b, bc, ab, c, ca, bc, ab, bc, ca });
                }
                faces = nf;
            }
            var rng = new System.Random(seed);
            for (int i = 0; i < verts.Count; i++)
                verts[i] = verts[i].normalized * 0.5f * (1f + (float)(rng.NextDouble() * 2.0 - 1.0) * jitter);
            return Flat(name, verts.ToArray(), faces.ToArray());
        }

        /// <summary>Malla con vértices sin compartir (normales por cara: facetada aunque el shader no lo haga).</summary>
        static Mesh Flat(string name, Vector3[] v, int[] f)
        {
            var V = new Vector3[f.Length];
            var T = new int[f.Length];
            for (int i = 0; i < f.Length; i++) { V[i] = v[f[i]]; T[i] = i; }
            var m = new Mesh { name = name, vertices = V, triangles = T };
            m.RecalculateNormals();
            m.RecalculateBounds();
            return m;
        }
    }
}
