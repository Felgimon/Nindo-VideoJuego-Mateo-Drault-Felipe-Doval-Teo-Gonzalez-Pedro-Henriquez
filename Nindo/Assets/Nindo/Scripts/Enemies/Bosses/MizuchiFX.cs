using UnityEngine;
using UnityEngine.Rendering;

namespace Nindo
{
    /// <summary>
    /// Agua de los ataques de Mizuchi con el mismo shader de la Cascada Kohan (Nindo/Waterfall: vetas posterizadas que
    /// corren, espuma que crece hacia la punta, facetas que agarran la luna): el chorro, los pilares que caen del cielo y la
    /// ola. Así los ataques se leen como "la cascada en manos del koi" y no como efectos aparte. Mallas armadas una vez
    /// (la ola se rearma solo cuando cambian sus huecos), sin asignaciones por frame.
    /// </summary>
    static class KoiWater
    {
        static Shader shader;
        static bool searched;
        static Material glowLine;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() { shader = null; searched = false; glowLine = null; }

        /// <summary>Aditivo con color por vértice y sin la textura de punto suave: las estelas y el rayo se ven parejos
        /// de punta a punta (con el punto suave se apagaban en los extremos de la línea).</summary>
        public static Material GlowLine
        {
            get
            {
                if (glowLine == null)
                {
                    glowLine = FXMaterials.MakeParticle("KoiGlowLine", true);
                    glowLine.SetTexture("_BaseMap", Texture2D.whiteTexture);
                    glowLine.SetTexture("_MainTex", Texture2D.whiteTexture);
                }
                return glowLine;
            }
        }

        /// <summary>Material propio (cada efecto avanza su _FlowPhase). Sin el shader, agua celeste translúcida.</summary>
        public static Material Make(string name, float turbulence, float foamLip, float foamBase)
        {
            if (!searched)
            {
                searched = true;
                shader = Resources.Load<Shader>("Shaders/NindoWaterfall");
                if (shader != null && !shader.isSupported) shader = null;
            }
            if (shader == null) return FXMaterials.MakeUnlitTransparent(name, new Color(0.55f, 0.85f, 0.95f, 0.75f), false);
            var m = new Material(shader) { name = name };
            m.SetFloat("_Turbulence", turbulence);
            m.SetFloat("_FoamLip", foamLip);
            m.SetFloat("_FoamBase", foamBase);
            m.SetFloat("_Sway", 0f);
            return m;
        }

        static readonly int IdFlowPhase = Shader.PropertyToID("_FlowPhase"), IdCorrupt = Shader.PropertyToID("_Corrupt"),
            IdAlpha = Shader.PropertyToID("_Alpha"), IdIntensity = Shader.PropertyToID("_Intensity");

        public static void Drive(Material m, float phase, float corrupt, float alpha, float intensity = 1.2f)
        {
            if (m == null) return;
            m.SetFloat(IdFlowPhase, phase);
            m.SetFloat(IdCorrupt, corrupt);
            m.SetFloat(IdAlpha, alpha);
            m.SetFloat(IdIntensity, intensity);
        }

        /// <summary>
        /// Cilindro facetado unitario (radio 1) a lo largo de +Z (0..1) o +Y. Colores como la cortina: r = avance del agua
        /// (0.08 en la boca → 0.88 en la punta: más espuma al final), b = azar por columna. uv = (metros del contorno,
        /// "segundos de vuelo" a lo largo).
        /// </summary>
        public static Mesh Cylinder(string name, int sides, int rings, bool alongY, float uvLength, bool flowToEnd)
        {
            int cols = sides + 1;
            var v = new Vector3[cols * (rings + 1)];
            var n = new Vector3[v.Length];
            var c = new Color[v.Length];
            var uv = new Vector2[v.Length];
            var rnd = new System.Random(sides * 31 + rings);
            var colRnd = new float[cols];
            for (int i = 0; i < sides; i++) colRnd[i] = (float)rnd.NextDouble();
            colRnd[sides] = colRnd[0];
            for (int r = 0; r <= rings; r++)
            {
                float t = r / (float)rings;
                for (int i = 0; i < cols; i++)
                {
                    float a = i / (float)sides * Mathf.PI * 2f;
                    Vector3 radial = alongY ? new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a)) : new Vector3(Mathf.Cos(a), Mathf.Sin(a), 0f);
                    Vector3 axis = alongY ? new Vector3(0f, t, 0f) : new Vector3(0f, 0f, t);
                    int k = r * cols + i;
                    v[k] = axis + radial;
                    n[k] = radial;
                    float prog = flowToEnd ? t : 1f - t;
                    c[k] = new Color(Mathf.Lerp(0.08f, 0.88f, prog), 0f, colRnd[i], 1f);
                    uv[k] = new Vector2(a, prog * uvLength);
                }
            }
            var tri = new int[sides * rings * 6];
            int q = 0;
            for (int r = 0; r < rings; r++)
                for (int i = 0; i < sides; i++)
                {
                    int a0 = r * cols + i, a1 = a0 + 1, b0 = a0 + cols, b1 = b0 + 1;
                    tri[q++] = a0; tri[q++] = b0; tri[q++] = a1;
                    tri[q++] = a1; tri[q++] = b0; tri[q++] = b1;
                }
            var m = new Mesh { name = name, vertices = v, normals = n, colors = c, uv = uv, triangles = tri };
            m.RecalculateBounds();
            return m;
        }

        public static MeshRenderer Renderer(GameObject go, Mesh mesh, Material mat)
        {
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
            return mr;
        }
    }

    /// <summary>El chorro del koi: un cilindro de agua a presión desde la boca, con rocío y una luz fría en la punta.</summary>
    public class KoiBeam : MonoBehaviour
    {
        const float Radius = 0.6f;
        Material mat;
        MeshRenderer mr;
        Light tipLight;
        float phase, show, showTarget, sprayTimer, corrupt, deck;
        Vector3 from, dir;
        float length;

        public static KoiBeam Create(Transform parent)
        {
            var go = new GameObject("KoiBeam");
            go.transform.SetParent(parent, false);
            var b = go.AddComponent<KoiBeam>();
            b.mat = KoiWater.Make("KoiBeam", 0.35f, 0.3f, 0.9f);
            b.mr = KoiWater.Renderer(go, KoiWater.Cylinder("KoiBeam", 8, 10, false, 5f, true), b.mat);
            b.mr.enabled = false;
            var lg = new GameObject("Tip");
            lg.transform.SetParent(go.transform, false);
            b.tipLight = lg.AddComponent<Light>();
            b.tipLight.type = LightType.Point; b.tipLight.color = new Color(0.66f, 0.9f, 1f); b.tipLight.range = 6f; b.tipLight.shadows = LightShadows.None;
            b.tipLight.enabled = false;
            return b;
        }

        void OnDestroy() { if (mat != null) Destroy(mat); }

        /// <summary>Prende (o mueve) el chorro: de la boca 'origin' hacia 'direction' hasta 'len' m, apuntando al piso al final.</summary>
        public void Fire(Vector3 origin, Vector3 direction, float len, float corruption, float deckY)
        {
            from = origin; dir = direction.Flat().normalized; length = len; corrupt = corruption; deck = deckY;
            showTarget = 1f;
        }

        public void Stop() => showTarget = 0f;
        public bool Visible => show > 0.01f;

        void Update()
        {
            float dt = Time.deltaTime;
            // entra en 0.06 s (golpe de presión) y se corta en 0.15 s
            show = Mathf.MoveTowards(show, showTarget, dt / (showTarget > show ? 0.06f : 0.15f));
            bool on = show > 0.01f;
            mr.enabled = on;
            tipLight.enabled = on;
            if (!on) return;
            phase += dt * 15f;
            KoiWater.Drive(mat, phase, corrupt, 0.95f);
            Vector3 tip = from + dir * length; tip.y = deck + 0.2f;
            Vector3 ax = tip - from;
            transform.SetPositionAndRotation(from, Quaternion.LookRotation(ax.sqrMagnitude > 0.01f ? ax : Vector3.forward));
            float r = Radius * Mathf.Lerp(0.3f, 1f, show) * (1f + 0.06f * Mathf.Sin(Time.time * 40f));
            transform.localScale = new Vector3(r, r, ax.magnitude);
            tipLight.transform.position = tip + Vector3.up * 0.6f;
            tipLight.intensity = 5f * show;
            sprayTimer -= dt;
            if (sprayTimer <= 0f && showTarget > 0f)
            {
                sprayTimer = 0.05f;
                WaterSplash.Spray(tip, Vector3.up * 0.8f + dir * 0.6f, 6, 7f, 0.22f);
            }
        }
    }

    /// <summary>Pilar de agua que cae del cielo (fase 2): baja en 0.35 s, revienta, queda un instante y se deshace.</summary>
    public class KoiPillar : MonoBehaviour
    {
        const float Top = 18f;
        Material mat;
        MeshRenderer mr;
        float phase, t, fall, radius;
        float deckY;
        bool active;

        public bool Busy => active;

        public static KoiPillar Create(Transform parent)
        {
            var go = new GameObject("KoiPillar");
            go.transform.SetParent(parent, false);
            var p = go.AddComponent<KoiPillar>();
            p.mat = KoiWater.Make("KoiPillar", 0.6f, 0.2f, 0.85f);
            p.mr = KoiWater.Renderer(go, KoiWater.Cylinder("KoiPillar", 8, 8, true, 9f, false), p.mat);
            p.mr.enabled = false;
            return p;
        }

        void OnDestroy() { if (mat != null) Destroy(mat); }

        /// <summary>Empieza a caer: toca el piso en 'fallTime' s.</summary>
        public void Drop(Vector3 center, float r, float fallTime, float deck)
        {
            transform.position = new Vector3(center.x, deck + Top, center.z);
            radius = r; fall = Mathf.Max(0.05f, fallTime); deckY = deck; t = 0f; active = true;
            mr.enabled = true;
        }

        public void Hide() { active = false; mr.enabled = false; }

        void Update()
        {
            if (!active) return;
            float dt = Time.deltaTime;
            t += dt;
            phase += dt * 9f;
            // cae acelerando; después de tocar queda 0.35 s y se adelgaza hacia arriba en 0.45 s
            float k = Mathf.Clamp01(t / fall);
            float bottom = Mathf.Lerp(deckY + Top, deckY - 0.2f, k * k);
            float after = t - fall;
            float thin = after > 0.35f ? Mathf.Clamp01((after - 0.35f) / 0.45f) : 0f;
            if (thin >= 1f) { Hide(); return; }
            float top = deckY + Top;
            if (thin > 0f) bottom = Mathf.Lerp(deckY - 0.2f, top, thin * thin);
            float h = Mathf.Max(0.1f, top - bottom);
            float r = Mathf.Lerp(radius * 0.72f, radius, k) * (1f - 0.5f * thin);
            transform.position = new Vector3(transform.position.x, bottom, transform.position.z);
            transform.localScale = new Vector3(r, h, r);
            // translúcido y más angosto que su disco (0.75): con la cámara alta la columna tapaba a Kaito y al disco justo
            // antes del golpe (render de prueba); el chapuzón del impacto sí llega al borde del disco
            KoiWater.Drive(mat, phase, 0.35f, 0.72f * (1f - thin), 1.4f);
        }
    }

    /// <summary>
    /// La ola de la cascada (fase 2): una cresta curvada de 22 m que cruza la plataforma de norte a sur, con dos huecos
    /// de espuma baja donde no pega (la respuesta sin dash). Perfil de 9 puntos extruido a lo ancho.
    /// </summary>
    public class KoiWave : MonoBehaviour
    {
        // perfil (z adelante, y arriba) desde la espalda hasta el frente; el frente (la base de adelante) está en z = 0.6
        static readonly Vector2[] Profile =
        {
            new Vector2(-2.4f, 0f), new Vector2(-1.6f, 0.9f), new Vector2(-0.9f, 1.9f), new Vector2(-0.2f, 2.55f),
            new Vector2(0.45f, 2.5f), new Vector2(0.85f, 2.05f), new Vector2(0.7f, 1.55f), new Vector2(0.35f, 1.2f), new Vector2(0.6f, 0f),
        };
        public const float FrontOffset = 0.6f, HalfWidth = 11f;
        const float TroughHeight = 0.16f;
        Material mat;
        MeshRenderer mr;
        Mesh mesh;
        float phase, alpha, crestTimer;
        Vector3[] verts;
        Color[] cols;
        Vector2[] uvs;
        int[] tris;
        float[] gapX = new float[2];
        float gapHalf;
        bool on;

        public static KoiWave Create(Transform parent)
        {
            var go = new GameObject("KoiWave");
            go.transform.SetParent(parent, false);
            var w = go.AddComponent<KoiWave>();
            w.mat = KoiWater.Make("KoiWave", 0.5f, 0.2f, 0.9f);
            w.mesh = new Mesh { name = "KoiWave" };
            w.mesh.MarkDynamic();
            w.mr = KoiWater.Renderer(go, w.mesh, w.mat);
            w.mr.enabled = false;
            return w;
        }

        void OnDestroy() { if (mat != null) Destroy(mat); if (mesh != null) Destroy(mesh); }

        /// <summary>Arma la ola con sus dos huecos (x local, m) de medio ancho 'half'. 'pos' = centro del frente, 'fwd' = hacia donde rueda.</summary>
        public void Build(float gap0, float gap1, float half)
        {
            gapX[0] = gap0; gapX[1] = gap1; gapHalf = half;
            // columnas cada 0.5 m: los bordes de los huecos quedan definidos sin escalones raros
            const int Cols = 45;
            int rows = Profile.Length;
            int nv = Cols * rows;
            if (verts == null || verts.Length != nv)
            {
                verts = new Vector3[nv]; cols = new Color[nv]; uvs = new Vector2[nv];
                tris = new int[(Cols - 1) * (rows - 1) * 6];
            }
            var rnd = new System.Random(7);
            float arc = 0f;
            var arcAt = new float[rows];
            for (int j = 1; j < rows; j++) { arc += Vector2.Distance(Profile[j], Profile[j - 1]); arcAt[j] = arc; }
            for (int i = 0; i < Cols; i++)
            {
                float x = Mathf.Lerp(-HalfWidth, HalfWidth, i / (float)(Cols - 1));
                float h = Height(x);
                float cr = (float)rnd.NextDouble();
                for (int j = 0; j < rows; j++)
                {
                    Vector2 pr = Profile[j];
                    // en los huecos la ola es un colchón de espuma: baja y achatada
                    float y = pr.y * h;
                    float z = Mathf.Lerp(pr.x * 0.6f, pr.x, h);
                    int k = i * rows + j;
                    verts[k] = new Vector3(x, y, z);
                    float prog = Mathf.Lerp(0.1f, 0.9f, arcAt[j] / arc);
                    cols[k] = new Color(h < 0.5f ? 0.9f : prog, 0f, cr, 1f);
                    uvs[k] = new Vector2(x, 0.2f + arcAt[j] * 0.5f);   // sin la línea de luna del labio (uv.y ~ 0)
                }
            }
            int q = 0;
            for (int i = 0; i < Cols - 1; i++)
                for (int j = 0; j < rows - 1; j++)
                {
                    int a0 = i * rows + j, a1 = a0 + 1, b0 = a0 + rows, b1 = b0 + 1;
                    tris[q++] = a0; tris[q++] = a1; tris[q++] = b0;
                    tris[q++] = a1; tris[q++] = b1; tris[q++] = b0;
                }
            mesh.Clear();
            mesh.vertices = verts; mesh.colors = cols; mesh.uv = uvs; mesh.triangles = tris;
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
        }

        /// <summary>Alto relativo de la ola en x (1 = cresta entera, TroughHeight = hueco), con una rampa de 0.6 m.</summary>
        float Height(float x)
        {
            float h = 1f;
            for (int g = 0; g < 2; g++)
            {
                float d = Mathf.Abs(x - gapX[g]) - gapHalf;
                float k = Mathf.Clamp01((d + 0.3f) / 0.6f);
                h = Mathf.Min(h, Mathf.Lerp(TroughHeight, 1f, k));
            }
            // los extremos se hunden (no corta en seco a los costados de la plataforma)
            float edge = Mathf.Clamp01((HalfWidth - Mathf.Abs(x)) / 1.5f);
            return h * Mathf.Lerp(0.35f, 1f, edge);
        }

        /// <summary>Ubica la ola: 'front' = punto del frente sobre la plataforma, 'fwd' = hacia donde rueda.</summary>
        public void Place(Vector3 front, Vector3 fwd, float visibility)
        {
            alpha = Mathf.Clamp01(visibility);
            on = alpha > 0.01f;
            mr.enabled = on;
            if (!on) return;
            transform.SetPositionAndRotation(front - fwd * FrontOffset, Quaternion.LookRotation(fwd, Vector3.up));
            transform.localScale = new Vector3(1f, Mathf.Lerp(0.4f, 1f, alpha), 1f);
            crestTimer -= Time.deltaTime;
            if (crestTimer <= 0f)
            {
                // espuma que se vuela de la cresta (solo donde hay cresta)
                crestTimer = 0.07f;
                Vector3 right = Vector3.Cross(Vector3.up, fwd);
                for (int i = 0; i < 4; i++)
                {
                    float x = Random.Range(-HalfWidth + 1f, HalfWidth - 1f);
                    if (Height(x) < 0.6f) continue;
                    Vector3 crest = transform.position + right * x + fwd * 0.5f + Vector3.up * 2.5f * transform.localScale.y;
                    WaterSplash.Spray(crest, fwd * 0.8f + Vector3.up * 0.5f, 2, 6f, 0.25f);
                }
            }
        }

        public void Hide() { on = false; mr.enabled = false; }

        void Update()
        {
            if (!on) return;
            phase += Time.deltaTime * 6f;
            KoiWater.Drive(mat, phase, 0.3f, 0.95f * alpha, 1.5f);
        }
    }

    /// <summary>
    /// El koi bajo el agua: una sombra larga que nada a ras del agua y la estela en V de la aleta dorsal. Es lo que dice
    /// por dónde va a salir mientras el modelo está escondido.
    /// </summary>
    public class KoiGhost : MonoBehaviour
    {
        MeshRenderer mr;
        MaterialPropertyBlock mpb;
        float wakeTimer, ringTimer, alpha;
        Vector3 last;

        public static KoiGhost Create(Transform parent)
        {
            var go = new GameObject("KoiGhost");
            go.transform.SetParent(parent, false);
            var g = go.AddComponent<KoiGhost>();
            go.AddComponent<MeshFilter>().sharedMesh = WaterSplash.Quad;
            g.mr = go.AddComponent<MeshRenderer>();
            g.mr.sharedMaterial = FXMaterials.Alpha;
            g.mr.shadowCastingMode = ShadowCastingMode.Off;
            g.mr.receiveShadows = false;
            g.mr.enabled = false;
            g.mpb = new MaterialPropertyBlock();
            return g;
        }

        public void Show(bool on) { if (!on) alpha = 0f; mr.enabled = on; }

        /// <summary>Lo mueve a 'pos' (a ras del agua) mirando a 'fwd'; deja la estela.</summary>
        public void Swim(Vector3 pos, Vector3 fwd, float waterY)
        {
            fwd = fwd.Flat();
            if (fwd.sqrMagnitude < 1e-4f) fwd = transform.forward;
            Vector3 p = new Vector3(pos.x, waterY + 0.08f, pos.z);
            transform.SetPositionAndRotation(p, Quaternion.LookRotation(fwd.normalized, Vector3.up));
            transform.localScale = new Vector3(2.1f, 1f, 6.2f);
            alpha = Mathf.MoveTowards(alpha, 1f, Time.deltaTime * 4f);
            var c = new Color(0.02f, 0.07f, 0.1f, 0.62f * alpha);
            mpb.SetColor("_BaseColor", c); mpb.SetColor("_Color", c);
            mr.SetPropertyBlock(mpb);
            float speed = (p - last).magnitude / Mathf.Max(1e-4f, Time.deltaTime);
            last = p;
            wakeTimer -= Time.deltaTime;
            if (wakeTimer <= 0f && speed > 1f)
            {
                // la V: dos chorritos hacia los costados desde la aleta dorsal, un poco detrás de la cabeza
                wakeTimer = 0.06f;
                Vector3 right = Vector3.Cross(Vector3.up, fwd.normalized);
                Vector3 fin = p + fwd.normalized * 0.8f + Vector3.up * 0.1f;
                WaterSplash.Spray(fin, (right - fwd.normalized * 0.6f) * 0.7f + Vector3.up * 0.5f, 2, 4.5f, 0.18f);
                WaterSplash.Spray(fin, (-right - fwd.normalized * 0.6f) * 0.7f + Vector3.up * 0.5f, 2, 4.5f, 0.18f);
            }
            ringTimer -= Time.deltaTime;
            if (ringTimer <= 0f) { ringTimer = 0.28f; RingWave.Spawn(p, 1.6f, new Color(0.7f, 0.9f, 1f, 0.5f), 0.6f); }
        }
    }

    /// <summary>Rayo violeta del sello (transición a la fase 2): una línea quebrada que se rearma unas veces y se apaga.</summary>
    public class SealBolt : MonoBehaviour
    {
        const int Points = 14;
        LineRenderer lr;
        readonly Vector3[] pts = new Vector3[Points];
        Vector3 a, b;
        float t, life, jag;

        public static void Strike(Vector3 from, Vector3 to, float seconds)
        {
            var go = new GameObject("SealBolt");
            var s = go.AddComponent<SealBolt>();
            s.lr = go.AddComponent<LineRenderer>();
            s.lr.positionCount = Points;
            s.lr.sharedMaterial = KoiWater.GlowLine;
            s.lr.widthCurve = new AnimationCurve(new Keyframe(0f, 0.9f), new Keyframe(1f, 0.35f));
            var c = new Color(0.85f, 0.6f, 1f, 1f);
            s.lr.startColor = c * 2.2f; s.lr.endColor = c * 2.8f;
            s.lr.shadowCastingMode = ShadowCastingMode.Off;
            s.a = from; s.b = to; s.life = seconds;
            s.Rebuild();
            Game.FX?.FlashLight(Vector3.Lerp(from, to, 0.6f), new Color(0.75f, 0.5f, 1f), 30f, 45f, 0.45f);
            Game.FX?.Screen?.WhiteFlash(0.35f);
            Game.Audio?.Play("thunder", to, 1f, 0.04f);
            Game.Camera?.Shake(0.6f);
        }

        void Rebuild()
        {
            Vector3 d = b - a;
            Vector3 side = Vector3.Cross(d.normalized, Vector3.forward);
            if (side.sqrMagnitude < 0.01f) side = Vector3.right;
            side.Normalize();
            Vector3 side2 = Vector3.Cross(d.normalized, side);
            for (int i = 0; i < Points; i++)
            {
                float k = i / (float)(Points - 1);
                float amp = Mathf.Sin(k * Mathf.PI) * d.magnitude * 0.06f;
                pts[i] = a + d * k + (side * Random.Range(-1f, 1f) + side2 * Random.Range(-1f, 1f)) * amp;
            }
            lr.SetPositions(pts);
        }

        void Update()
        {
            t += Time.deltaTime;
            jag -= Time.deltaTime;
            if (jag <= 0f) { jag = 0.05f; Rebuild(); }
            float k = Mathf.Clamp01(t / life);
            lr.widthMultiplier = 1f - k * k;
            if (t >= life) Destroy(gameObject);
        }
    }
}
