using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Capa de cuerpo del Gran Koi (Art/Characters/Mizuchi/Mizuchi.fbx, rig de Tools/Blender/bosses/mizuchi/koi_rig.py).
    /// Corre en LateUpdate, después del Animator, y solo SUMA encima de lo que dejó el clip:
    ///  * fase: el FBX trae los dos cuerpos (Body_P1 Tancho blanco, Body_P2 corrompido) y sin esto se dibujaban juntos;
    ///  * nado creíble: la columna de atrás sigue el rumbo de hace un instante (la cola recorre el camino de la cabeza),
    ///    el cuerpo se inclina hacia la curva y la cabeza mira a Kaito (±25°) mientras ronda o se cubre. Todo eso se
    ///    apaga en 0.1 s durante los golpes: las poses de ataque del clip son las que avisan y no se tocan;
    ///  * la luz violeta del sello que late en el lomo (marca al jefe en la oscuridad y el punto del remate);
    ///  * la silueta de golpe: una polilínea hocico-cabeza-lomo-cola-abanico con su grosor, para que la katana le entre en
    ///    cualquier parte de los 7.5 m (Enemy.HurtCenter) y no solo cerca del centro;
    ///  * oculto (bajo el agua), el espejo de agua del piso solo cuando está apoyado, y la forma de dragón dorado del final.
    /// Sin asignaciones por frame: los huesos y las listas se buscan una vez.
    /// </summary>
    public class KoiBody : MonoBehaviour
    {
        // columna de atrás: spine_b1..b4 y tail. Cuánto sigue cada vértebra el rumbo viejo (más hacia la cola) y con qué
        // retraso: la cola dobla por donde pasó la cabeza 0.25 s antes
        static readonly float[] FollowWeight = { 0.35f, 0.5f, 0.65f, 0.8f, 0.9f };
        const float FollowLag = 0.05f, FollowMax = 30f;
        const float BankPerDegS = 0.08f, BankMax = 20f;
        const float LookMax = 25f;
        // silueta de golpe (radio de cada punto: hocico, cabeza, lomo, cintura, pedúnculo, abanico de la cola)
        static readonly float[] HurtRadius = { 0.55f, 0.95f, 1.0f, 0.75f, 0.45f, 0.8f };
        static readonly Color SealPurple = new Color(0.753f, 0.541f, 1f);   // glow_purple

        Transform owner;
        Transform bodyBone, spineF, head, jaw, seal, flukeL1, flukeL2, flukeR2;
        readonly Transform[] back = new Transform[5];
        SkinnedMeshRenderer p1, p2, ripple;
        Material[] p2Materials;
        Light sealLight;

        /// <summary>Puntas que no son huesos (para las estelas y la silueta): fin de la mandíbula, del abanico y de las aletas.</summary>
        public Transform JawTip { get; private set; }
        public Transform FlukeTip { get; private set; }
        public Transform PecTipL { get; private set; }
        public Transform PecTipR { get; private set; }

        // historia del rumbo de la raíz (1 s a cualquier framerate razonable)
        const int HistoryLen = 128;
        readonly float[] histTime = new float[HistoryLen];
        readonly float[] histYaw = new float[HistoryLen];
        int histHead, histCount;
        float lastYaw, yawRate;
        readonly float[] followAngle = new float[5];

        float weight, weightTarget;
        float lookWeight, lookWeightTarget;
        Vector3 lookAt;
        int phase;
        bool hidden, dragon, rippleOn = true;
        float sealBase = 1.5f, sealFlare, sealFlareUntil;

        readonly Vector3[] hurt = new Vector3[6];

        public int Phase => phase;
        public bool Hidden => hidden;
        public Vector3 Snout => JawTip != null ? JawTip.position : owner.position + owner.forward * 2.9f + Vector3.up * 1.3f;
        public Vector3 SealPosition => seal != null ? seal.position : owner.position + Vector3.up * 3f;
        public Transform Seal => seal;
        public Transform Head => head;
        public Transform Tail => back[4];

        public static KoiBody Attach(Transform model, Transform owner)
        {
            var kb = model.gameObject.AddComponent<KoiBody>();
            kb.Init(model, owner);
            return kb;
        }

        void Init(Transform model, Transform own)
        {
            owner = own;
            bodyBone = Find(model, "body");
            spineF = Find(model, "spine_f");
            head = Find(model, "head");
            jaw = Find(model, "jaw");
            seal = Find(model, "seal");
            string[] backNames = { "spine_b1", "spine_b2", "spine_b3", "spine_b4", "tail" };
            for (int i = 0; i < back.Length; i++) back[i] = Find(model, backNames[i]);
            flukeL1 = Find(model, "fluke_L1");
            flukeL2 = Find(model, "fluke_L2");
            flukeR2 = Find(model, "fluke_R2");
            foreach (var r in model.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                if (r.name == "Body_P1") p1 = r;
                else if (r.name == "Body_P2") p2 = r;
                else if (r.name == "Ripple") ripple = r;
                // el clip mueve el cuerpo hasta 4.7 m (Freed) y la raíz vuela en los saltos: con los bounds de la pose de
                // reposo se recortaba fuera de cámara. Un solo jefe en pantalla: el costo es chico
                r.updateWhenOffscreen = true;
            }
            if (p2 != null) p2Materials = p2.sharedMaterials;

            // las puntas se calculan en la pose de reposo (todavía no corrió el Animator): prolongación de cada hueso
            JawTip = Tip("JawTip", jaw, head, 0.6f);
            FlukeTip = Tip("FlukeTip", flukeL2, flukeL1, 1f);
            PecTipL = Tip("PecTipL", Find(model, "pec_L3"), Find(model, "pec_L2"), 1f);
            PecTipR = Tip("PecTipR", Find(model, "pec_R3"), Find(model, "pec_R2"), 1f);

            if (seal != null)
            {
                var lg = new GameObject("SealLight");
                lg.transform.SetParent(seal, false);
                lg.transform.localPosition = Vector3.zero;
                sealLight = lg.AddComponent<Light>();
                sealLight.type = LightType.Point;
                sealLight.color = SealPurple;
                sealLight.range = 5f;
                sealLight.intensity = sealBase;
                sealLight.shadows = LightShadows.None;
            }
            lastYaw = owner.eulerAngles.y;
            SetPhase(0);
        }

        internal static Transform Find(Transform t, string name)
        {
            if (t.name == name) return t;
            for (int i = 0; i < t.childCount; i++)
            {
                var r = Find(t.GetChild(i), name);
                if (r != null) return r;
            }
            return null;
        }

        /// <summary>Punto fijo al hueso 'bone', 'k' veces su largo más allá (dirección padre → hueso).</summary>
        static Transform Tip(string name, Transform bone, Transform parent, float k)
        {
            if (bone == null || parent == null) return bone;
            var go = new GameObject(name);
            go.transform.SetParent(bone, false);
            Vector3 dir = bone.position - parent.position;
            go.transform.position = bone.position + dir * k;
            return go.transform;
        }

        // ------------------------------------------------------------------ API (MizuchiBoss)
        /// <summary>0 = Tancho (fase 1), 1 = corrompido (fases 2 y 3).</summary>
        public void SetPhase(int p)
        {
            phase = p;
            if (dragon) SetDragon(null);
            sealBase = p == 0 ? 1.5f : 2.4f;
            ApplyVisibility();
        }

        /// <summary>Bajo el agua (zambullida): nada del modelo se dibuja; la luz del sello tampoco.</summary>
        public void SetHidden(bool h)
        {
            hidden = h;
            ApplyVisibility();
        }

        /// <summary>El anillo de espuma del piso solo cuando apoya (en un salto quedaba colgado debajo de la panza).</summary>
        public void SetRipple(bool on)
        {
            if (rippleOn == on) return;
            rippleOn = on;
            ApplyVisibility();
        }

        void ApplyVisibility()
        {
            bool showP2 = phase >= 1 || dragon;
            if (p1 != null) p1.enabled = !hidden && !showP2;
            if (p2 != null) p2.enabled = !hidden && showP2;
            if (ripple != null) ripple.enabled = !hidden && rippleOn && !dragon;
            if (sealLight != null) sealLight.enabled = !hidden && !dragon && sealBase > 0f;
        }

        /// <summary>Destello del sello (cambio de fase): 'mul' veces la luz durante 'seconds' (tiempo de juego).</summary>
        public void FlareSeal(float mul, float seconds)
        {
            sealFlare = mul;
            sealFlareUntil = Time.time + seconds;
        }

        /// <summary>La estaca salió: el sello ya no brilla.</summary>
        public void SealOut()
        {
            sealBase = 0f;
            ApplyVisibility();
        }

        /// <summary>Forma del dragón liberado: el cuerpo corrompido (cuernos, bigotes) con un material fantasma dorado;
        /// null vuelve a sus materiales.</summary>
        public void SetDragon(Material ghost)
        {
            dragon = ghost != null;
            if (p2 != null && p2Materials != null)
            {
                if (dragon)
                {
                    var mats = new Material[p2Materials.Length];
                    for (int i = 0; i < mats.Length; i++) mats[i] = ghost;
                    p2.sharedMaterials = mats;
                    p2.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                }
                else
                {
                    p2.sharedMaterials = p2Materials;
                    p2.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;
                }
            }
            ApplyVisibility();
        }

        /// <summary>Peso de la capa de nado (1 rondando, 0 golpeando o varado) y a dónde mira la cabeza (null = al frente).</summary>
        public void SetDrive(float procedural, float look, Vector3 lookTarget)
        {
            weightTarget = Mathf.Clamp01(procedural);
            lookWeightTarget = Mathf.Clamp01(look);
            lookAt = lookTarget;
        }

        /// <summary>Punto de la silueta (en planta) más cercano a 'p' y el grosor del cuerpo ahí.</summary>
        public Vector3 Closest(Vector3 p, out float radius)
        {
            Vector3 best = hurt[0];
            float bestD = float.MaxValue;
            radius = HurtRadius[0];
            for (int i = 0; i < hurt.Length - 1; i++)
            {
                Vector3 a = hurt[i], b = hurt[i + 1];
                Vector3 ab = (b - a).Flat();
                float t = ab.sqrMagnitude > 1e-4f ? Mathf.Clamp01(Vector3.Dot((p - a).Flat(), ab) / ab.sqrMagnitude) : 0f;
                Vector3 c = a + (b - a) * t;
                float d = (p - c).Flat().sqrMagnitude;
                if (d < bestD) { bestD = d; best = c; radius = Mathf.Lerp(HurtRadius[i], HurtRadius[i + 1], t); }
            }
            return best;
        }

        // ------------------------------------------------------------------ frame
        void LateUpdate()
        {
            float dt = Time.deltaTime;
            if (owner == null) return;
            if (dt > 0f)
            {
                // las capas entran y salen en ~0.1 s (un golpe que arranca no hereda la curva del nado)
                weight = Mathf.MoveTowards(weight, weightTarget, dt * 10f);
                lookWeight = Mathf.MoveTowards(lookWeight, lookWeightTarget, dt * 6f);
                RecordYaw(dt);
            }
            if (weight > 0.001f) ApplyFollow();
            if (lookWeight > 0.001f) ApplyLook();
            UpdateSeal();
            UpdateHurt();
        }

        void RecordYaw(float dt)
        {
            float yaw = owner.eulerAngles.y;
            yawRate = Mathf.Lerp(yawRate, Mathf.DeltaAngle(lastYaw, yaw) / dt, 1f - Mathf.Exp(-12f * dt));
            lastYaw = yaw;
            histHead = (histHead + 1) % HistoryLen;
            histTime[histHead] = Time.time;
            histYaw[histHead] = yaw;
            if (histCount < HistoryLen) histCount++;
        }

        /// <summary>Rumbo de la raíz hace 'ago' segundos (interpolado; si la historia no llega, el más viejo).</summary>
        float YawAgo(float ago)
        {
            float t = Time.time - ago;
            int idx = histHead;
            for (int n = 0; n < histCount - 1; n++)
            {
                int prev = (idx - 1 + HistoryLen) % HistoryLen;
                if (histTime[prev] <= t)
                {
                    float span = histTime[idx] - histTime[prev];
                    float k = span > 1e-5f ? (t - histTime[prev]) / span : 0f;
                    return histYaw[prev] + Mathf.DeltaAngle(histYaw[prev], histYaw[idx]) * k;
                }
                idx = prev;
            }
            return histYaw[idx];
        }

        void ApplyFollow()
        {
            float now = owner.eulerAngles.y;
            Vector3 up = owner.up;
            // cada vértebra apunta hacia el rumbo viejo; como los huesos se heredan, se aplica la diferencia con la anterior
            float prev = 0f;
            for (int i = 0; i < back.Length; i++)
            {
                var b = back[i];
                if (b == null) continue;
                float target = Mathf.Clamp(Mathf.DeltaAngle(now, YawAgo(FollowLag * (i + 1))), -FollowMax, FollowMax) * FollowWeight[i] * weight;
                followAngle[i] = target;
                float local = target - prev;
                prev = target;
                b.rotation = Quaternion.AngleAxis(local, up) * b.rotation;
            }
            // se inclina hacia la curva (de costado el koi se lee de arriba como un abanico que vira)
            if (bodyBone != null)
            {
                float bank = -Mathf.Clamp(yawRate * BankPerDegS, -BankMax, BankMax) * weight;
                bodyBone.rotation = Quaternion.AngleAxis(bank, owner.forward) * bodyBone.rotation;
            }
        }

        void ApplyLook()
        {
            if (head == null) return;
            Vector3 to = (lookAt - owner.position).Flat();
            if (to.sqrMagnitude < 0.25f) return;
            float ang = Mathf.Clamp(Vector3.SignedAngle(owner.forward.Flat(), to, Vector3.up), -LookMax, LookMax) * lookWeight;
            Vector3 up = owner.up;
            if (spineF != null) spineF.rotation = Quaternion.AngleAxis(ang * 0.4f, up) * spineF.rotation;
            head.rotation = Quaternion.AngleAxis(ang * 0.6f, up) * head.rotation;
        }

        void UpdateSeal()
        {
            if (sealLight == null || !sealLight.enabled) return;
            float flare = Time.time < sealFlareUntil ? Mathf.Lerp(1f, sealFlare, Mathf.Clamp01((sealFlareUntil - Time.time) / 0.4f)) : 1f;
            // late lento, como un corazón cansado (en la fase 2 más fuerte)
            float beat = 0.78f + 0.22f * Mathf.Sin(Time.time * 2.4f) + 0.12f * Mathf.Max(0f, Mathf.Sin(Time.time * 4.8f + 1f));
            sealLight.intensity = sealBase * beat * flare;
        }

        void UpdateHurt()
        {
            Vector3 root = owner.position;
            hurt[0] = JawTip != null ? JawTip.position : root + owner.forward * 2.9f;
            hurt[1] = head != null ? head.position : root + owner.forward * 1.35f;
            hurt[2] = back[0] != null ? back[0].position : root;
            hurt[3] = back[2] != null ? back[2].position : root - owner.forward * 1.7f;
            hurt[4] = back[4] != null ? back[4].position : root - owner.forward * 2.75f;
            // abanico: entre las dos puntas
            if (flukeL2 != null && flukeR2 != null) hurt[5] = (flukeL2.position + flukeR2.position) * 0.5f;
            else hurt[5] = root - owner.forward * 3.6f;
        }
    }
}
