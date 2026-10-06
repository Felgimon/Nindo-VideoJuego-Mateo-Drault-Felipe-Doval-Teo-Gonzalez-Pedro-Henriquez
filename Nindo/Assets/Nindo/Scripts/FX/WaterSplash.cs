using UnityEngine;
using UnityEngine.Rendering;

namespace Nindo
{
    /// <summary>
    /// Salpicones de agua para los cuerpos grandes que caen en la plataforma mojada (Mizuchi varado, panzadas,
    /// el koi que aterriza después de un salto). Mismo lenguaje que la Cascada Kohan: gotas estiradas, bloques de
    /// espuma facetados (shader Nindo/Spray), una nube blanda, anillo sobre el agua y una mancha mojada que se seca.
    /// Tres sistemas persistentes en espacio mundo con Emit() a mano: cada gota sale con la velocidad que le toca
    /// según su lugar a lo largo del cuerpo (el agua se escapa por los costados).
    /// El temblor de cámara y el daño los decide quien llama.
    /// </summary>
    public static class WaterSplash
    {
        static Transform root;
        static ParticleSystem drops, chunks, puffs;
        static Mesh quad;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() { root = null; drops = chunks = puffs = null; quad = null; }

        /// <summary>Un cuerpo largo golpea el agua/la plataforma: 'bodyDir' = eje del cuerpo, 'size' 1 = el koi entero (~6 m).</summary>
        public static void Beached(Vector3 pos, Vector3 bodyDir, float size = 1f)
        {
            if (!Ensure()) return;
            bodyDir.y = 0f;
            bodyDir = bodyDir.sqrMagnitude > 1e-4f ? bodyDir.normalized : Vector3.forward;
            Vector3 side = Vector3.Cross(Vector3.up, bodyDir);
            float len = 6f * size;
            // sábanas de gotas por los dos costados, a lo largo de todo el cuerpo
            int n = Mathf.RoundToInt(44 * size);
            for (int i = 0; i < n; i++)
            {
                float along = Random.Range(-0.5f, 0.5f) * len;
                float s = Random.value < 0.5f ? -1f : 1f;
                Vector3 v = side * s * Random.Range(2.5f, 6f) + Vector3.up * Random.Range(3f, 7.5f) + bodyDir * Random.Range(-1f, 1f);
                Drop(pos + bodyDir * along + side * s * Random.Range(0.3f, 0.9f) * size, v, Random.Range(0.12f, 0.3f));
            }
            // corona en el centro (donde pegó más fuerte)
            for (int i = 0; i < Mathf.RoundToInt(18 * size); i++)
            {
                Vector3 dir = Quaternion.AngleAxis(Random.Range(0f, 360f), Vector3.up) * Quaternion.AngleAxis(Random.Range(5f, 40f), Vector3.right) * Vector3.up;
                Drop(pos + Vector3.up * 0.2f, dir * Random.Range(6f, 10f), Random.Range(0.15f, 0.32f));
            }
            for (int i = 0; i < Mathf.RoundToInt(10 * size); i++)
                Chunk(pos + bodyDir * Random.Range(-0.5f, 0.5f) * len + side * Random.Range(-1f, 1f) * size,
                      Vector3.up * Random.Range(1f, 3.2f) + side * Random.Range(-1.5f, 1.5f), Random.Range(0.45f, 1.05f) * Mathf.Sqrt(size));
            for (int i = 0; i < 6; i++)
                Puff(pos + bodyDir * Random.Range(-0.4f, 0.4f) * len + Vector3.up * 0.5f, Random.Range(2f, 3.6f) * Mathf.Sqrt(size));
            RingWave.Spawn(pos, 3.6f * size, new Color(0.75f, 0.92f, 1f, 0.8f), 0.6f);
            var flood = KohanFalls.Instance != null ? KohanFalls.Instance.Flood : null;
            if (flood != null)
            {
                flood.Ripple(pos);
                flood.Ripple(pos + bodyDir * len * 0.35f);
                flood.Ripple(pos - bodyDir * len * 0.35f);
            }
            WetStain.Spawn(pos, bodyDir, len, 2.6f * size);
            Game.Audio?.Play("water_splash", pos, Mathf.Clamp01(0.7f + 0.3f * size));
        }

        /// <summary>Salpicón chico: un aletazo del koi varado, una cola que golpea, una gota grande que cae.</summary>
        public static void Flop(Vector3 pos, float size = 0.6f)
        {
            if (!Ensure()) return;
            for (int i = 0; i < Mathf.RoundToInt(22 * size); i++)
            {
                Vector3 dir = Quaternion.AngleAxis(Random.Range(0f, 360f), Vector3.up) * Quaternion.AngleAxis(Random.Range(20f, 60f), Vector3.right) * Vector3.up;
                Drop(pos + Vector3.up * 0.1f, dir * Random.Range(3f, 6.5f), Random.Range(0.1f, 0.22f));
            }
            for (int i = 0; i < 3; i++)
                Chunk(pos + Random.insideUnitSphere * 0.5f * size, Vector3.up * Random.Range(1f, 2.4f), Random.Range(0.3f, 0.6f) * size);
            RingWave.Spawn(pos, 1.8f * size, new Color(0.75f, 0.92f, 1f, 0.7f), 0.45f);
            if (KohanFalls.Instance != null && KohanFalls.Instance.Flood != null) KohanFalls.Instance.Flood.Ripple(pos);
            Game.Audio?.Play("water_splash", pos, 0.45f);
        }

        // ------------------------------------------------------------------ emisión
        static void Drop(Vector3 p, Vector3 v, float size)
        {
            drops.Emit(new ParticleSystem.EmitParams { position = p, velocity = v, startSize = size, startLifetime = Random.Range(0.7f, 1.1f), startColor = new Color(0.86f, 0.94f, 1f, 0.9f) }, 1);
        }

        static void Chunk(Vector3 p, Vector3 v, float size)
        {
            chunks.Emit(new ParticleSystem.EmitParams
            {
                position = p, velocity = v, startLifetime = Random.Range(0.55f, 0.95f),
                startSize3D = Vector3.one * size, rotation3D = new Vector3(Random.Range(0f, 360f), Random.Range(0f, 360f), 0f), startColor = Color.white,
            }, 1);
        }

        static void Puff(Vector3 p, float size)
        {
            puffs.Emit(new ParticleSystem.EmitParams
            {
                position = p, velocity = Vector3.up * Random.Range(0.3f, 0.8f) + Random.insideUnitSphere * 0.6f, startSize = size,
                startLifetime = Random.Range(1.2f, 1.8f), rotation = Random.Range(0f, 360f), startColor = new Color(0.82f, 0.88f, 0.94f, 0.3f),
            }, 1);
        }

        static bool Ensure()
        {
            if (root != null) return true;
            // vive en la escena de juego: con la escena se destruye y se vuelve a armar la próxima vez
            root = new GameObject("[WaterSplash]").transform;
            drops = Make("SplashDrops", FXMaterials.Alpha, 400, null, 1.2f);
            var r = drops.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.Stretch; r.velocityScale = 0.045f; r.lengthScale = 1.3f;
            Fade(drops, 1f, 0f);
            var spray = FallsAssets.SplashSpray;
            chunks = Make("SplashFoam", spray != null ? spray : FXMaterials.Alpha, 80, spray != null ? FallsAssets.Ico : null, 0.8f);
            Fade(chunks, 1f, 0f);
            var sz = chunks.sizeOverLifetime; sz.enabled = true;
            sz.size = new ParticleSystem.MinMaxCurve(1f, new AnimationCurve(new Keyframe(0f, 0.8f), new Keyframe(1f, 1.4f)));
            puffs = Make("SplashMist", FXMaterials.Alpha, 40, null, -0.05f);
            Fade(puffs, 1f, 0f);
            var ps = puffs.sizeOverLifetime; ps.enabled = true;
            ps.size = new ParticleSystem.MinMaxCurve(1f, new AnimationCurve(new Keyframe(0f, 0.6f), new Keyframe(1f, 1.5f)));
            return true;
        }

        static ParticleSystem Make(string name, Material mat, int max, Mesh mesh, float gravity)
        {
            var ps = FXFactory.NewSystem(name, root);
            var m = ps.main;
            m.loop = true; m.duration = 5f; m.maxParticles = max; m.gravityModifier = gravity;
            m.simulationSpace = ParticleSystemSimulationSpace.World;
            m.startSize3D = mesh != null; m.startRotation3D = mesh != null;
            var em = ps.emission; em.enabled = false;
            var sh = ps.shape; sh.enabled = false;
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.sharedMaterial = mat;
            if (mesh != null) { r.renderMode = ParticleSystemRenderMode.Mesh; r.mesh = mesh; r.alignment = ParticleSystemRenderSpace.World; }
            ps.Play();
            return ps;
        }

        static void Fade(ParticleSystem ps, float a0, float a1)
        {
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(a0, 0f), new GradientAlphaKey(a0 * 0.85f, 0.6f), new GradientAlphaKey(a1, 1f) });
            col.color = new ParticleSystem.MinMaxGradient(g);
        }

        internal static Mesh Quad
        {
            get
            {
                if (quad != null) return quad;
                quad = new Mesh { name = "StainQuad" };
                quad.vertices = new[] { new Vector3(-0.5f, 0, -0.5f), new Vector3(0.5f, 0, -0.5f), new Vector3(-0.5f, 0, 0.5f), new Vector3(0.5f, 0, 0.5f) };
                quad.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) };
                quad.triangles = new[] { 0, 2, 1, 2, 3, 1 };
                quad.RecalculateBounds();
                return quad;
            }
        }
    }

    /// <summary>Mancha mojada oscura (blanda, estirada a lo largo del cuerpo) que se seca en ~5 s.</summary>
    public class WetStain : MonoBehaviour
    {
        static readonly Color Wet = new Color(0.05f, 0.08f, 0.12f, 0.45f);
        static readonly int IdBaseColor = Shader.PropertyToID("_BaseColor"), IdColor = Shader.PropertyToID("_Color");
        static readonly RaycastHit[] hits = new RaycastHit[8];
        MeshRenderer mr;
        MaterialPropertyBlock mpb;
        float t, life = 5f;

        public static void Spawn(Vector3 pos, Vector3 along, float length, float width)
        {
            var go = new GameObject("WetStain");
            // apoyada en lo que haya debajo (la plataforma), apenas encima para no pelear con la madera; se ignora
            // el cuerpo del que cayó (el koi está encima de la mancha)
            Vector3 p = pos;
            int n = Physics.RaycastNonAlloc(pos + Vector3.up * 1.5f, Vector3.down, hits, 4f, ~0, QueryTriggerInteraction.Ignore);
            float best = float.MaxValue;
            for (int i = 0; i < n; i++)
            {
                var col = hits[i].collider;
                if (col.GetComponentInParent<Enemy>() != null || col.GetComponentInParent<PlayerController>() != null) continue;
                if (hits[i].distance < best) { best = hits[i].distance; p = hits[i].point; }
            }
            go.transform.SetPositionAndRotation(p + Vector3.up * 0.03f, Quaternion.LookRotation(along, Vector3.up));
            go.transform.localScale = new Vector3(width, 1f, length * 1.1f);
            go.AddComponent<MeshFilter>().sharedMesh = WaterSplash.Quad;
            var s = go.AddComponent<WetStain>();
            s.mr = go.AddComponent<MeshRenderer>();
            s.mr.sharedMaterial = FXMaterials.Alpha;
            s.mr.shadowCastingMode = ShadowCastingMode.Off;
            s.mr.receiveShadows = false;
            s.mpb = new MaterialPropertyBlock();
            s.Update();
        }

        void Update()
        {
            t += Time.deltaTime;
            var c = Wet; c.a *= 1f - Mathf.SmoothStep(0f, 1f, t / life);
            mpb.SetColor(IdBaseColor, c); mpb.SetColor(IdColor, c);
            mr.SetPropertyBlock(mpb);
            if (t >= life) Destroy(gameObject);
        }
    }
}
