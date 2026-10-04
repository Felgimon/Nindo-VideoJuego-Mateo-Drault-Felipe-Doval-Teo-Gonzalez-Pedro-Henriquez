using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Construye por código las plantillas de partículas (chispas, polvo, humo, hojas, fuego...).
    /// Al estar en código no dependen de prefabs y se pueden ajustar fácilmente.
    /// Las plantillas viven bajo un objeto inactivo y se clonan con Pool.
    /// </summary>
    public static class FXFactory
    {
        static Transform templatesRoot;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() { templatesRoot = null; }

        public static Transform TemplatesRoot
        {
            get
            {
                if (templatesRoot == null)
                {
                    var go = new GameObject("[FX Templates]");
                    go.SetActive(false);
                    Object.DontDestroyOnLoad(go);
                    templatesRoot = go.transform;
                }
                return templatesRoot;
            }
        }

        public static ParticleSystem NewSystem(string name, Transform parent = null)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent != null ? parent : TemplatesRoot, false);
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = ps.main;
            main.playOnAwake = true;
            main.loop = false;
            main.duration = 1f;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.scalingMode = ParticleSystemScalingMode.Hierarchy;
            main.maxParticles = 200;
            var em = ps.emission; em.rateOverTime = 0f;
            var r = go.GetComponent<ParticleSystemRenderer>();
            r.sharedMaterial = FXMaterials.Additive;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.receiveShadows = false;
            return ps;
        }

        static void Burst(ParticleSystem ps, int min, int max)
        {
            var em = ps.emission;
            em.SetBursts(new[] { new ParticleSystem.Burst(0f, (short)min, (short)max) });
        }

        static Gradient Fade(Color a, Color b, float alphaEnd = 0f)
        {
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(a, 0f), new GradientColorKey(b, 1f) },
                      new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(0.8f, 0.5f), new GradientAlphaKey(alphaEnd, 1f) });
            return g;
        }

        static void ColorOverLife(ParticleSystem ps, Color a, Color b)
        {
            var col = ps.colorOverLifetime; col.enabled = true;
            col.color = new ParticleSystem.MinMaxGradient(Fade(a, b));
        }

        static void SizeOverLife(ParticleSystem ps, float start, float end)
        {
            var s = ps.sizeOverLifetime; s.enabled = true;
            s.size = new ParticleSystem.MinMaxCurve(1f, new AnimationCurve(new Keyframe(0f, start), new Keyframe(1f, end)));
        }

        // ------------------------------------------------------------------ plantillas
        public static GameObject Sparks(Color c, int min, int max, float speed, string name)
        {
            var ps = NewSystem(name);
            var m = ps.main;
            m.duration = 0.4f;
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.12f, 0.32f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(speed * 0.5f, speed);
            m.startSize = new ParticleSystem.MinMaxCurve(0.04f, 0.09f);
            m.startColor = c;
            m.gravityModifier = 1.2f;
            Burst(ps, min, max);
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Cone; sh.angle = 38f; sh.radius = 0.05f;
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.Stretch; r.velocityScale = 0.06f; r.lengthScale = 1.5f;
            ColorOverLife(ps, c, new Color(1f, 0.4f, 0.1f));
            return ps.gameObject;
        }

        public static GameObject FlashSprite(Color c, float size, float life, string name)
        {
            var ps = NewSystem(name);
            var m = ps.main;
            m.duration = life; m.startLifetime = life; m.startSpeed = 0f; m.startSize = size; m.startColor = c;
            Burst(ps, 1, 1);
            var sh = ps.shape; sh.enabled = false;
            SizeOverLife(ps, 0.6f, 1.4f);
            ColorOverLife(ps, c, c);
            return ps.gameObject;
        }

        public static GameObject Puff(Color c, int count, float size, float life, float speed, bool additiveBlend, string name, float gravity = -0.05f)
        {
            var ps = NewSystem(name);
            var m = ps.main;
            m.duration = life;
            m.startLifetime = new ParticleSystem.MinMaxCurve(life * 0.6f, life);
            m.startSpeed = new ParticleSystem.MinMaxCurve(speed * 0.3f, speed);
            m.startSize = new ParticleSystem.MinMaxCurve(size * 0.6f, size);
            m.startColor = c;
            m.gravityModifier = gravity;
            m.startRotation = new ParticleSystem.MinMaxCurve(0f, Mathf.PI * 2f);
            Burst(ps, count, count + 4);
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Sphere; sh.radius = size * 0.3f;
            SizeOverLife(ps, 0.5f, 1.3f);
            ColorOverLife(ps, c, c * 0.8f);
            ps.GetComponent<ParticleSystemRenderer>().sharedMaterial = additiveBlend ? FXMaterials.Additive : FXMaterials.Alpha;
            return ps.gameObject;
        }

        public static GameObject Leaves(Color a, Color b, int count, float radius, float life, string name)
        {
            var ps = NewSystem(name);
            var m = ps.main;
            m.duration = life;
            m.startLifetime = new ParticleSystem.MinMaxCurve(life * 0.7f, life);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.5f, 2f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.08f, 0.18f);
            m.startColor = new ParticleSystem.MinMaxGradient(a, b);
            m.startRotation = new ParticleSystem.MinMaxCurve(0f, Mathf.PI * 2f);
            m.simulationSpace = ParticleSystemSimulationSpace.Local;
            m.gravityModifier = -0.05f;
            Burst(ps, count, count + 10);
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Circle; sh.radius = radius; sh.radiusThickness = 0.4f;
            sh.rotation = new Vector3(90f, 0f, 0f);
            var vel = ps.velocityOverLifetime; vel.enabled = true; vel.space = ParticleSystemSimulationSpace.Local;
            vel.orbitalY = new ParticleSystem.MinMaxCurve(7f, 10f);
            vel.radial = new ParticleSystem.MinMaxCurve(-0.4f, 0.4f);
            vel.y = new ParticleSystem.MinMaxCurve(0.6f, 2.2f);
            var rot = ps.rotationOverLifetime; rot.enabled = true; rot.z = new ParticleSystem.MinMaxCurve(-6f, 6f);
            ColorOverLife(ps, Color.white, Color.white);
            ps.GetComponent<ParticleSystemRenderer>().sharedMaterial = FXMaterials.Alpha;
            return ps.gameObject;
        }

        public static GameObject Rising(Color a, Color b, int count, float radius, float life, string name)
        {
            var ps = NewSystem(name);
            var m = ps.main;
            m.duration = life;
            m.startLifetime = new ParticleSystem.MinMaxCurve(life * 0.5f, life);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.2f, 1f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.05f, 0.14f);
            m.startColor = new ParticleSystem.MinMaxGradient(a, b);
            m.gravityModifier = -0.35f;
            Burst(ps, count, count + 6);
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Circle; sh.radius = radius; sh.rotation = new Vector3(90f, 0f, 0f);
            ColorOverLife(ps, a, b);
            return ps.gameObject;
        }

        public static GameObject Inward(Color c, int count, float radius, float life, string name)
        {
            var ps = NewSystem(name);
            var m = ps.main;
            m.duration = life;
            m.startLifetime = life;
            m.startSpeed = -radius / life;
            m.startSize = new ParticleSystem.MinMaxCurve(0.06f, 0.14f);
            m.startColor = c;
            m.simulationSpace = ParticleSystemSimulationSpace.Local;
            Burst(ps, count, count);
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Sphere; sh.radius = radius; sh.radiusThickness = 0f;
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.Stretch; r.velocityScale = 0.08f; r.lengthScale = 1f;
            ColorOverLife(ps, c, Color.white);
            return ps.gameObject;
        }

        /// <summary>Fuego a lo largo de la hoja (local: de 0 a 'tipLocal').</summary>
        public static ParticleSystem FireAlongBlade(Transform parent, Vector3 tipLocal)
        {
            var ps = NewSystem("BladeFire", parent);
            var go = ps.gameObject;
            go.transform.localPosition = tipLocal * 0.5f;
            if (tipLocal.sqrMagnitude > 0.0001f) go.transform.localRotation = Quaternion.FromToRotation(Vector3.right, tipLocal.normalized);
            var m = ps.main;
            m.loop = true; m.duration = 1f; m.playOnAwake = false;
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.18f, 0.38f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.1f, 0.5f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.12f, 0.3f);
            m.startColor = new ParticleSystem.MinMaxGradient(new Color(1f, 0.75f, 0.25f), new Color(1f, 0.35f, 0.1f));
            m.gravityModifier = -0.6f;
            m.maxParticles = 120;
            var em = ps.emission; em.rateOverTime = 70f;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.SingleSidedEdge; sh.radius = tipLocal.magnitude * 0.5f;
            SizeOverLife(ps, 1f, 0.2f);
            ColorOverLife(ps, new Color(1f, 0.85f, 0.4f), new Color(0.9f, 0.2f, 0.05f));
            return ps;
        }

        /// <summary>Luciérnagas ambientales (loop) en un área.</summary>
        public static ParticleSystem Fireflies(Transform parent, Vector3 size, int max = 40)
        {
            var ps = NewSystem("Fireflies", parent);
            ps.gameObject.transform.SetParent(parent, false);
            var m = ps.main;
            m.loop = true; m.duration = 5f; m.playOnAwake = true; m.prewarm = true;
            m.startLifetime = new ParticleSystem.MinMaxCurve(4f, 8f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.05f, 0.3f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.05f, 0.11f);
            m.startColor = new ParticleSystem.MinMaxGradient(new Color(0.85f, 1f, 0.45f), new Color(1f, 0.9f, 0.4f));
            m.maxParticles = max;
            m.simulationSpace = ParticleSystemSimulationSpace.World;
            var em = ps.emission; em.rateOverTime = max / 6f;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = size;
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.6f; noise.frequency = 0.35f; noise.scrollSpeed = 0.2f;
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(1f, 0.15f), new GradientAlphaKey(0.2f, 0.35f), new GradientAlphaKey(1f, 0.55f), new GradientAlphaKey(0.3f, 0.75f), new GradientAlphaKey(0f, 1f) });
            col.color = g;
            ps.Play();
            return ps;
        }

        /// <summary>Humo de incienso / chimenea (loop).</summary>
        public static ParticleSystem Smoke(Transform parent, float scale = 1f)
        {
            var ps = NewSystem("Smoke", parent);
            var m = ps.main;
            m.loop = true; m.duration = 4f; m.playOnAwake = true; m.prewarm = true;
            m.startLifetime = new ParticleSystem.MinMaxCurve(2.5f, 4f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.15f, 0.35f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.25f * scale, 0.6f * scale);
            m.startColor = new Color(0.75f, 0.78f, 0.85f, 0.18f);
            m.startRotation = new ParticleSystem.MinMaxCurve(0f, Mathf.PI * 2f);
            m.gravityModifier = -0.04f;
            m.maxParticles = 30;
            var em = ps.emission; em.rateOverTime = 3f;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Cone; sh.angle = 8f; sh.radius = 0.05f; sh.rotation = new Vector3(-90f, 0f, 0f);
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.25f; noise.frequency = 0.4f;
            SizeOverLife(ps, 0.6f, 2f);
            var col = ps.colorOverLifetime; col.enabled = true; col.color = new ParticleSystem.MinMaxGradient(Fade(Color.white, Color.white));
            ps.GetComponent<ParticleSystemRenderer>().sharedMaterial = FXMaterials.Alpha;
            ps.Play();
            return ps;
        }
    }

    /// <summary>Anillo que se expande sobre el piso (ondas de choque, parry, furia).</summary>
    public class RingWave : MonoBehaviour
    {
        float t, life = 0.45f, radius = 4f;
        Color color = Color.white;
        MeshRenderer mr;
        MaterialPropertyBlock mpb;
        static Mesh ringMesh;

        public static RingWave Spawn(Vector3 pos, float radius, Color c, float life = 0.45f)
        {
            var go = new GameObject("RingWave");
            go.transform.position = pos + Vector3.up * 0.06f;
            var rw = go.AddComponent<RingWave>();
            rw.radius = radius; rw.color = c; rw.life = life;
            go.AddComponent<MeshFilter>().sharedMesh = RingMesh;
            rw.mr = go.AddComponent<MeshRenderer>();
            rw.mr.sharedMaterial = FXMaterials.Additive;
            rw.mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            rw.mpb = new MaterialPropertyBlock();
            rw.Update();
            return rw;
        }

        static Mesh RingMesh
        {
            get
            {
                if (ringMesh != null) return ringMesh;
                const int N = 40;
                var v = new Vector3[N * 2]; var uv = new Vector2[N * 2]; var tri = new int[N * 6];
                for (int i = 0; i < N; i++)
                {
                    float a = i / (float)N * Mathf.PI * 2f;
                    Vector3 d = new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a));
                    v[i * 2] = d * 0.82f; v[i * 2 + 1] = d;
                    uv[i * 2] = new Vector2(0.5f, 0.5f); uv[i * 2 + 1] = new Vector2(0.5f, 0.5f);
                    int j = (i + 1) % N;
                    tri[i * 6] = i * 2; tri[i * 6 + 1] = j * 2; tri[i * 6 + 2] = i * 2 + 1;
                    tri[i * 6 + 3] = i * 2 + 1; tri[i * 6 + 4] = j * 2; tri[i * 6 + 5] = j * 2 + 1;
                }
                ringMesh = new Mesh { name = "Ring", vertices = v, uv = uv, triangles = tri };
                ringMesh.RecalculateBounds();
                return ringMesh;
            }
        }

        void Update()
        {
            t += Time.deltaTime;
            float k = Mathf.Clamp01(t / life);
            float s = Mathf.Lerp(0.2f, radius, 1f - (1f - k) * (1f - k));
            transform.localScale = new Vector3(s, 1f, s);
            var c = color; c.a *= 1f - k;
            mpb.SetColor("_BaseColor", c); mpb.SetColor("_Color", c);
            mr.SetPropertyBlock(mpb);
            if (t >= life) Destroy(gameObject);
        }
    }

    /// <summary>Tajo luminoso recto (corte del viento, ejecuciones).</summary>
    public class SlashLineFX : MonoBehaviour
    {
        float t, life = 0.35f;
        LineRenderer lr;
        Color color;

        public static void Spawn(Vector3 a, Vector3 b, Color c, float width = 0.35f, float life = 0.35f)
        {
            var go = new GameObject("SlashLine");
            var s = go.AddComponent<SlashLineFX>();
            s.lr = go.AddComponent<LineRenderer>();
            s.lr.positionCount = 2;
            s.lr.SetPosition(0, a); s.lr.SetPosition(1, b);
            s.lr.sharedMaterial = FXMaterials.Additive;
            s.lr.widthCurve = new AnimationCurve(new Keyframe(0f, 0f), new Keyframe(0.5f, 1f), new Keyframe(1f, 0f));
            s.lr.widthMultiplier = width;
            s.lr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            s.lr.numCapVertices = 2;
            s.color = c; s.life = life;
            s.lr.startColor = c; s.lr.endColor = c;
        }

        void Update()
        {
            t += Time.unscaledDeltaTime;
            float k = t / life;
            var c = color; c.a *= 1f - k;
            lr.startColor = c; lr.endColor = c;
            lr.widthMultiplier *= 1f + Time.unscaledDeltaTime * 2f;
            if (t >= life) Destroy(gameObject);
        }
    }

    /// <summary>Imágenes residuales del dash (mallas horneadas, reutilizadas).</summary>
    public class AfterImage : MonoBehaviour
    {
        MeshFilter mf; MeshRenderer mr; Mesh mesh;
        float t, life = 0.35f;
        MaterialPropertyBlock mpb;
        Color color;

        public static AfterImage Create()
        {
            var go = new GameObject("AfterImage");
            var a = go.AddComponent<AfterImage>();
            a.mf = go.AddComponent<MeshFilter>();
            a.mr = go.AddComponent<MeshRenderer>();
            a.mr.sharedMaterial = FXMaterials.Ghost;
            a.mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            a.mr.receiveShadows = false;
            a.mesh = new Mesh { name = "AfterImage" };
            a.mf.sharedMesh = a.mesh;
            a.mpb = new MaterialPropertyBlock();
            return a;
        }

        public void Bake(SkinnedMeshRenderer smr, Color c, float lifetime)
        {
            smr.BakeMesh(mesh, true);
            var tr = smr.transform;
            // BakeMesh ignora la escala: la reaplicamos
            transform.SetPositionAndRotation(tr.position, tr.rotation);
            transform.localScale = Vector3.one;
            color = c; life = lifetime; t = 0f;
            gameObject.SetActive(true);
            Update();
        }

        void Update()
        {
            t += Time.deltaTime;
            var c = color; c.a *= Mathf.Clamp01(1f - t / life);
            mpb.SetColor("_BaseColor", c); mpb.SetColor("_Color", c);
            mr.SetPropertyBlock(mpb);
            if (t >= life) gameObject.SetActive(false);
        }
    }
}
