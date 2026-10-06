using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Lo que tapa la pelea se disuelve con una trama (shader Nindo/Occluder Fade), sin tocar a los personajes:
    ///  * HUECO: lo que está entre la cámara y Kaito, el fijado, el jefe o quien está por pegar se disuelve solo en un
    ///    cono alrededor de cada uno (el resto del árbol o de la casa sigue entero y el lugar se sigue leyendo).
    ///  * CERCA: lo que se mete en los primeros 11 m delante de la cámara (copas de cedro, bambú, techos que en
    ///    pantalla ocupan media imagen) se disuelve entero. En el bambú del noreste la cámara a 20 m de altura pasa
    ///    por las copas de los cedros y los bambúes al sur del camino: tapaban media pantalla aunque Kaito se viera.
    /// Detecta con los volúmenes de Occluder (trigger en Ignore Raycast) unas 12 veces por segundo; la disolución
    /// entra en 0.18 s y sale en 0.45 s, y se queda 0.3 s más para no parpadear al rozar el borde.
    /// Si el shader no está (otra versión de URP), vuelve a lo de antes: el objeto queda "solo sombra".
    /// </summary>
    [DefaultExecutionOrder(510)]
    public class CameraOcclusion : MonoBehaviour
    {
        const float ScanInterval = 0.08f;
        /// <summary>Radio del barrido hacia cada personaje (m): un poco menos que el hueco a la altura del personaje.</summary>
        const float CastRadius = 1.0f;
        /// <summary>Profundidad de la zona "pegada a la cámara" (m): a 11 m algo se ve 2.2 veces más grande que en Kaito.</summary>
        const float NearDepth = 11f;
        const int OccluderMask = 1 << 2;   // Ignore Raycast: ahí viven solo los volúmenes de Occluder

        Camera cam;
        float scanTimer;
        readonly RaycastHit[] hits = new RaycastHit[48];
        readonly Collider[] overlaps = new Collider[64];
        readonly List<Occluder> active = new List<Occluder>(32);

        // huecos: xyz = punto del personaje (pecho), w = tangente de su radio angular visto desde la cámara
        static readonly int HolesId = Shader.PropertyToID("_NindoHoles");
        readonly Vector4[] holes = new Vector4[4];
        readonly Vector3[] holePoints = new Vector3[4];
        int holeCount;

        void Awake() => cam = GetComponent<Camera>();

        void OnDisable()
        {
            foreach (var o in active) if (o != null) o.Restore();
            active.Clear();
            for (int i = 0; i < holes.Length; i++) holes[i] = Vector4.zero;
            Shader.SetGlobalVectorArray(HolesId, holes);
        }

        void LateUpdate()
        {
            if (cam == null) return;
            float dt = Time.unscaledDeltaTime, now = Time.unscaledTime;
            CollectHoles();
            Shader.SetGlobalVectorArray(HolesId, holes);

            scanTimer -= dt;
            // en un plano cinemático la cámara está en otro lado: se deja de buscar y lo disuelto vuelve solo
            if (scanTimer <= 0f && Game.Camera != null && !Game.Camera.InShot)
            {
                scanTimer = ScanInterval;
                Scan(now);
            }
            for (int i = active.Count - 1; i >= 0; i--)
            {
                var o = active[i];
                if (o == null || !o.Tick(dt, now)) active.RemoveAt(i);
            }
        }

        // ------------------------------------------------------------------ a quién se protege
        void CollectHoles()
        {
            holeCount = 0;
            var p = Game.Player;
            if (p != null && p.IsAlive) AddHole(p.AimPoint, 1.25f);
            var lockE = p != null ? p.LockTarget : null;
            if (lockE != null && lockE.IsAlive) AddHole(lockE.AimPoint, BodyRadius(lockE));
            var combat = Game.Combat;
            var boss = combat != null ? combat.ActiveBoss : null;
            if (boss != null && boss.IsAlive && boss != lockE) AddHole(boss.AimPoint, BodyRadius(boss));
            if (combat != null)
            {
                // el que pega antes entre los que ya dibujan su aviso
                Enemy next = null;
                var list = combat.Engaged;
                for (int i = 0; i < list.Count; i++)
                {
                    var e = list[i];
                    if (e == null || e == lockE || e == boss || !e.InTell) continue;
                    if (next == null || e.StrikeEta < next.StrikeEta) next = e;
                }
                if (next != null) AddHole(next.AimPoint, BodyRadius(next));
            }
            for (int i = holeCount; i < holes.Length; i++) holes[i] = Vector4.zero;
        }

        static float BodyRadius(Enemy e) => Mathf.Max(1.2f, e.config.height * e.config.scale * 0.6f);

        void AddHole(Vector3 point, float radius)
        {
            if (holeCount >= holes.Length) return;
            float d = Vector3.Distance(cam.transform.position, point);
            if (d < 1f) return;
            holes[holeCount] = new Vector4(point.x, point.y, point.z, radius / d);
            holePoints[holeCount] = point;
            holeCount++;
        }

        // ------------------------------------------------------------------ búsqueda
        void Scan(float now)
        {
            Vector3 from = cam.transform.position;
            for (int h = 0; h < holeCount; h++)
            {
                Vector3 dir = holePoints[h] - from;
                float len = dir.magnitude - 0.6f;
                if (len <= 0.1f) continue;
                int n = Physics.SphereCastNonAlloc(from, CastRadius, dir.normalized, hits, len, OccluderMask, QueryTriggerInteraction.Collide);
                for (int i = 0; i < n; i++) Mark(hits[i].collider, false, now);
            }
            // la zona pegada a la cámara: la caja que envuelve el tronco de pirámide de los primeros NearDepth metros
            float halfH = NearDepth * Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad);
            var box = new Vector3(halfH * cam.aspect, halfH, NearDepth * 0.5f);
            int m = Physics.OverlapBoxNonAlloc(from + cam.transform.forward * (NearDepth * 0.5f), box, overlaps, cam.transform.rotation, OccluderMask, QueryTriggerInteraction.Collide);
            for (int i = 0; i < m; i++) Mark(overlaps[i], true, now);
        }

        void Mark(Collider c, bool near, float now)
        {
            if (c == null) return;
            var occ = c.GetComponentInParent<Occluder>();
            if (occ == null) return;
            if (occ.Mark(near, now)) active.Add(occ);
        }

        // ------------------------------------------------------------------ materiales
        static Shader fadeShader;
        static bool shaderChecked;
        static readonly Dictionary<Material, Material> variants = new Dictionary<Material, Material>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() { variants.Clear(); fadeShader = null; shaderChecked = false; }

        /// <summary>¿Se puede disolver con trama? (si no, Occluder usa el "solo sombra" de antes)</summary>
        public static bool FadeSupported
        {
            get
            {
                if (!shaderChecked)
                {
                    shaderChecked = true;
                    fadeShader = Resources.Load<Shader>("Shaders/NindoOccluderFade");
                    if (fadeShader != null && !fadeShader.isSupported) fadeShader = null;
                }
                return fadeShader != null;
            }
        }

        /// <summary>
        /// Versión "disolvible" de un material del mundo (una por material, compartida). Se copian a mano solo las
        /// propiedades que el shader entiende: CopyPropertiesFromMaterial arrastraba las palabras clave del Lit.
        /// Null si no hay versión (agua, partículas): ese submaterial se queda como está.
        /// </summary>
        public static Material FadeVariant(Material src)
        {
            if (src == null || !FadeSupported) return null;
            if (variants.TryGetValue(src, out var m)) return m;
            bool wind = src.HasProperty("_WindStrength");
            bool lit = src.HasProperty("_BaseMap") && src.HasProperty("_BaseColor");
            if (!lit || src.renderQueue >= (int)UnityEngine.Rendering.RenderQueue.Transparent) { variants[src] = null; return null; }
            m = new Material(fadeShader) { name = src.name + " (disolución)" };
            m.SetTexture("_BaseMap", src.GetTexture("_BaseMap"));
            m.SetTextureScale("_BaseMap", src.GetTextureScale("_BaseMap"));
            m.SetTextureOffset("_BaseMap", src.GetTextureOffset("_BaseMap"));
            m.SetColor("_BaseColor", src.GetColor("_BaseColor"));
            // emisión solo si el original la tiene prendida (el Lit ignora _EmissionColor sin la palabra clave)
            bool emissive = src.HasProperty("_EmissionColor") && (src.IsKeywordEnabled("_EMISSION") || src.shader.name != "Universal Render Pipeline/Lit");
            m.SetColor("_EmissionColor", emissive ? src.GetColor("_EmissionColor") : Color.black);
            if (emissive && src.HasProperty("_EmissionMap")) m.SetTexture("_EmissionMap", src.GetTexture("_EmissionMap"));
            if (wind)
            {
                foreach (var prop in WindProps) if (src.HasProperty(prop)) m.SetFloat(prop, src.GetFloat(prop));
                m.SetFloat("_NindoWind", 1f);
                m.EnableKeyword("_NINDO_WIND");
            }
            // el follaje es de doble cara (su shader tiene Cull Off fijo, sin propiedad)
            m.SetFloat("_Cull", src.HasProperty("_Cull") ? src.GetFloat("_Cull") : 0f);
            variants[src] = m;
            return m;
        }

        static readonly string[] WindProps = { "_WindStrength", "_WindSpeed", "_WindScale", "_Flutter", "_Wrap" };
    }

    /// <summary>
    /// Objeto que se disuelve cuando tapa la pelea (lo maneja CameraOcclusion). Crea un volumen trigger del tamaño de
    /// todo el modelo (la copa de un árbol no tiene collider) en la capa "Ignore Raycast", así solo lo detectan los
    /// barridos de la cámara y no molesta a la jugabilidad ni al NavMesh. Mientras se disuelve usa materiales
    /// "disolvibles" y un MaterialPropertyBlock propio; al terminar le devuelve sus materiales (vuelve al batching).
    /// </summary>
    public class Occluder : MonoBehaviour
    {
        /// <summary>Cuánto se disuelve: en el hueco queda 3/16 de la trama (se sigue viendo qué hay); pegado a la
        /// cámara 1/16 (ocupa media pantalla: con más puntos la trama ya se ve como ruido encima de la pelea).</summary>
        const float HoleFade = 0.82f, NearFade = 0.94f;
        const float FadeInTime = 0.18f, FadeOutTime = 0.45f, Linger = 0.3f;

        static readonly int FadeId = Shader.PropertyToID("_NindoFade");
        static readonly int HoleId = Shader.PropertyToID("_NindoHoleFade");
        static MaterialPropertyBlock block;

        /// <summary>
        /// Props sin la etiqueta "occluder" del manifest que igual tapan la pelea (medido con la cámara del juego sobre
        /// el mapa real: un acantilado del bosque tapaba a Kaito entero en el claro, la campana del bambú y el bambú
        /// joven de 2.5 m también). WorldBuilder les agrega el componente.
        /// </summary>
        public static bool AlsoOccludes(string propId) =>
            propId != null && (propId.StartsWith("cliff_") || propId == "temple_bell" || propId == "bamboo_young" || propId == "rock_pillar");

        Renderer[] rs;
        Material[][] originals;
        bool swapped, tracked, legacyHidden;
        float hole, near, holeUntil = -1f, nearUntil = -1f;

        void Awake()
        {
            rs = MeshRenderers();
            if (rs.Length == 0) return;
            Bounds b = rs[0].bounds;
            for (int i = 1; i < rs.Length; i++) b.Encapsulate(rs[i].bounds);
            var vol = new GameObject("OccluderVolume");
            vol.layer = 2; // Ignore Raycast
            vol.transform.SetParent(transform, false);
            vol.transform.SetPositionAndRotation(b.center, Quaternion.identity);
            var box = vol.AddComponent<BoxCollider>();
            box.isTrigger = true;
            Vector3 s = vol.transform.lossyScale;
            // un poco más chico que el AABB: que no se disuelva por rozarlo
            box.size = new Vector3(b.size.x / Mathf.Max(0.01f, s.x), b.size.y / Mathf.Max(0.01f, s.y), b.size.z / Mathf.Max(0.01f, s.z)) * 0.85f;
        }

        /// <summary>Solo mallas: humo, luciérnagas o fuego del prop son partículas y no se tocan.</summary>
        Renderer[] MeshRenderers()
        {
            var list = new List<Renderer>();
            foreach (var r in GetComponentsInChildren<Renderer>(true))
                if (r is MeshRenderer || r is SkinnedMeshRenderer) list.Add(r);
            return list.ToArray();
        }

        /// <summary>Lo vio un barrido de la cámara. Devuelve true si hay que empezar a seguirlo.</summary>
        public bool Mark(bool nearCamera, float now)
        {
            if (nearCamera) nearUntil = now + Linger; else holeUntil = now + Linger;
            if (tracked) return false;
            tracked = true;
            return true;
        }

        /// <summary>Avanza la disolución. False cuando volvió del todo y se puede dejar de seguir.</summary>
        public bool Tick(float dt, float now)
        {
            if (rs == null || rs.Length == 0) { tracked = false; return false; }
            float wantHole = now < holeUntil ? 1f : 0f, wantNear = now < nearUntil ? 1f : 0f;
            hole = Mathf.MoveTowards(hole, wantHole, dt / (wantHole > hole ? FadeInTime : FadeOutTime));
            near = Mathf.MoveTowards(near, wantNear, dt / (wantNear > near ? FadeInTime : FadeOutTime));
            bool visible = hole <= 0f && near <= 0f;
            if (!CameraOcclusion.FadeSupported)
            {
                SetLegacyHidden(!visible);
                if (visible) tracked = false;
                return !visible;
            }
            if (visible) { Restore(); return false; }
            if (!swapped) Swap();
            block ??= new MaterialPropertyBlock();
            // curva suave: entra y sale sin escalón
            float h = hole * hole * (3f - 2f * hole), n = near * near * (3f - 2f * near);
            for (int i = 0; i < rs.Length; i++)
            {
                if (rs[i] == null) continue;
                rs[i].GetPropertyBlock(block);
                block.SetFloat(HoleId, h * HoleFade);
                block.SetFloat(FadeId, n * NearFade);
                rs[i].SetPropertyBlock(block);
            }
            return true;
        }

        void Swap()
        {
            swapped = true;
            originals ??= new Material[rs.Length][];
            for (int i = 0; i < rs.Length; i++)
            {
                var r = rs[i];
                if (r == null) continue;
                var mats = r.sharedMaterials;
                originals[i] = mats;
                var fade = new Material[mats.Length];
                for (int k = 0; k < mats.Length; k++) fade[k] = CameraOcclusion.FadeVariant(mats[k]) ?? mats[k];
                r.sharedMaterials = fade;
            }
        }

        /// <summary>Vuelve a sus materiales y suelta el bloque de propiedades (y con eso, al batching normal).</summary>
        public void Restore()
        {
            hole = near = 0f;
            holeUntil = nearUntil = -1f;
            tracked = false;
            SetLegacyHidden(false);
            if (!swapped) return;
            swapped = false;
            for (int i = 0; i < rs.Length; i++)
            {
                if (rs[i] == null || originals[i] == null) continue;
                rs[i].sharedMaterials = originals[i];
                rs[i].SetPropertyBlock(null);
            }
        }

        /// <summary>Sin el shader: el objeto queda "solo sombra" mientras estorba (lo de antes).</summary>
        void SetLegacyHidden(bool h)
        {
            if (h == legacyHidden || rs == null) return;
            legacyHidden = h;
            foreach (var r in rs)
                if (r != null) r.shadowCastingMode = h ? UnityEngine.Rendering.ShadowCastingMode.ShadowsOnly : UnityEngine.Rendering.ShadowCastingMode.On;
        }
    }
}
