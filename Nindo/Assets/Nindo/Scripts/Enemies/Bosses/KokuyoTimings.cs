// Generado por Tools/Unity/kokuyo_timings.py desde Kokuyo.fbx.json: no editar a mano.
namespace Nindo
{
    /// <summary>Tiempos de un clip de Kokuyō tal como los mide el build de Blender (normalizados 0..1).</summary>
    public sealed class KokuyoClip
    {
        public readonly string State;
        public readonly int Frames;
        public readonly float Seconds, Apex, Contact, ActiveEnd, ReleaseRate, Reach;
        /// <summary>Metros que avanzó el transform en cada cuadro del clip (null = no se mueve).</summary>
        public readonly float[] Travel;
        /// <summary>Pose con la que empieza y con la que termina (READY, LOW_L, GUARD...): encadenar dos clips
        /// cuyas poses no coinciden pide un fundido más largo.</summary>
        public readonly string ChainFrom, ChainTo;
        readonly string[] eventNames;
        readonly float[] eventTimes;

        public KokuyoClip(string state, int frames, float seconds, float apex, float contact, float activeEnd, float releaseRate,
            float reach, float[] travel, string chainFrom, string chainTo, string[] eventNames, float[] eventTimes)
        {
            State = state; Frames = frames; Seconds = seconds; Apex = apex; Contact = contact; ActiveEnd = activeEnd;
            ReleaseRate = releaseRate; Reach = reach; Travel = travel; ChainFrom = chainFrom; ChainTo = chainTo;
            this.eventNames = eventNames; this.eventTimes = eventTimes;
        }

        /// <summary>Tiempo normalizado del primer evento con ese nombre (-1 si el clip no lo tiene).</summary>
        public float Event(string name)
        {
            for (int i = 0; i < eventNames.Length; i++) if (eventNames[i] == name) return eventTimes[i];
            return -1f;
        }

        /// <summary>Normalizado de un cuadro del clip.</summary>
        public float FrameNorm(float frame) => Frames > 0 ? frame / Frames : 0f;

        /// <summary>Metros avanzados en el tiempo normalizado 'n' (interpolado entre cuadros).</summary>
        public float TravelAt(float n)
        {
            if (Travel == null) return 0f;
            float x = UnityEngine.Mathf.Clamp(n, 0f, 1f) * Frames;
            int i = UnityEngine.Mathf.Min((int)x, Travel.Length - 1);
            int j = UnityEngine.Mathf.Min(i + 1, Travel.Length - 1);
            return Travel[i] + (Travel[j] - Travel[i]) * (x - i);
        }
    }

    public static class KokuyoTimings
    {
        public const float BindHeight = 4.511f;
        public static readonly KokuyoClip Idle = new KokuyoClip("Idle", 72, 2.4f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "", "", new string[0], new float[0]);
        public static readonly KokuyoClip Kesagiri = new KokuyoClip("Kesagiri", 36, 1.2f, 0.3889f, 0.5f, 0.5833f, 1.6f, 3.88f,
            new[] { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.225f, 0.45f, 0.6f, 0.72f, 0.8233f, 0.9267f, 1.03f, 1.1044f, 1.1575f, 1.1894f, 1.2f, 1.2f, 1.2f, 1.2f, 1.2f, 1.2f, 1.2f, 1.2f, 1.2f, 1.2f, 1.2f, 1.2f },
            "READY", "LOW_L", new string[] { "Apex", "Strike", "Step", "Step" }, new[] { 0.3889f, 0.5f, 0.5f, 0.9444f });
        public static readonly KokuyoClip RecoverL = new KokuyoClip("RecoverL", 15, 0.5f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "LOW_L", "READY", new string[0], new float[0]);
        public static readonly KokuyoClip RecoverHR = new KokuyoClip("RecoverHR", 12, 0.4f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "READY", "READY", new string[0], new float[0]);
        public static readonly KokuyoClip Gyakugiri = new KokuyoClip("Gyakugiri", 30, 1.0f, 0.3333f, 0.4667f, 0.5667f, 1.6f, 3.21f,
            new[] { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.3f, 0.45f, 0.6f, 0.7803f, 0.7982f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f },
            "LOW_L", "READY", new string[] { "Apex", "Strike", "Step" }, new[] { 0.3333f, 0.4667f, 0.4667f });
        public static readonly KokuyoClip Tsuki = new KokuyoClip("Tsuki", 46, 1.5333f, 0.4783f, 0.587f, 0.6522f, 0.4f, 4.37f,
            new[] { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.03f, 0.72f, 1.71f, 2.5f, 3.2f, 3.4111f, 3.4889f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f, 3.5f },
            "READY", "THRUST_END", new string[] { "Apex", "Step", "Strike", "Step" }, new[] { 0.4783f, 0.5217f, 0.587f, 0.587f });
        public static readonly KokuyoClip TsukiRecover = new KokuyoClip("TsukiRecover", 18, 0.6f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "THRUST_END", "READY", new string[] { "Step" }, new[] { 0.6667f });
        public static readonly KokuyoClip Ichimonji = new KokuyoClip("Ichimonji", 48, 1.6f, 0.4375f, 0.5833f, 0.6667f, 1.6f, 3.64f,
            null,
            "READY", "READY", new string[] { "Apex", "Strike" }, new[] { 0.4375f, 0.5833f });
        public static readonly KokuyoClip KabutoWari = new KokuyoClip("KabutoWari", 60, 2.0f, 0.3333f, 0.45f, 0.4833f, 1.6f, 3.98f,
            null,
            "READY", "READY", new string[] { "Apex", "Strike", "RiftStart", "Tug", "Tug", "BladeFree" }, new[] { 0.3333f, 0.45f, 0.45f, 0.55f, 0.65f, 0.7833f });
        public static readonly KokuyoClip ShadowSink = new KokuyoClip("ShadowSink", 21, 0.7f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "READY", "", new string[] { "ShadowPuddle" }, new[] { 0.381f });
        public static readonly KokuyoClip ShadowEmerge = new KokuyoClip("ShadowEmerge", 33, 1.1f, 0.2727f, 0.4242f, 0.5152f, 1.6f, 3.21f,
            new[] { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.3f, 0.45f, 0.6f, 0.7803f, 0.7982f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f, 0.8f },
            "", "READY", new string[] { "ShadowErupt", "Apex", "Strike" }, new[] { 0.1212f, 0.2727f, 0.4242f });
        public static readonly KokuyoClip Parried = new KokuyoClip("Parried", 30, 1.0f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            new[] { 0.0f, -0.146f, -0.2919f, -0.3569f, -0.4218f, -0.4867f, -0.5075f, -0.5284f, -0.5493f, -0.5701f, -0.5723f, -0.5779f, -0.5851f, -0.5923f, -0.5978f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f, -0.6f },
            "", "READY", new string[] { "Parried", "Step" }, new[] { 0.0f, 0.1667f });
        public static readonly KokuyoClip Flinch = new KokuyoClip("Flinch", 15, 0.5f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "", "READY", new string[0], new float[0]);
        public static readonly KokuyoClip Guard = new KokuyoClip("Guard", 36, 1.2f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "READY", "", new string[0], new float[0]);
        public static readonly KokuyoClip Counter = new KokuyoClip("Counter", 15, 0.5f, 0.1333f, 0.4667f, 0.6f, 1.6f, 2.43f,
            null,
            "GUARD", "LOW_L", new string[] { "Deflect", "Strike" }, new[] { 0.2f, 0.4667f });
        public static readonly KokuyoClip Roar = new KokuyoClip("Roar", 39, 1.3f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "", "READY", new string[] { "Roar" }, new[] { 0.359f });
        public static readonly KokuyoClip Kneel = new KokuyoClip("Kneel", 108, 3.6f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "READY", "READY", new string[] { "Armor", "Breath", "Breath", "Breath" }, new[] { 0.0926f, 0.213f, 0.4537f, 0.6944f });
        public static readonly KokuyoClip KneelRise = new KokuyoClip("KneelRise", 15, 0.5f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "KNEEL", "READY", new string[0], new float[0]);
        public static readonly KokuyoClip ShadowTear = new KokuyoClip("ShadowTear", 54, 1.8f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "READY", "READY", new string[] { "ShadowGrab", "CrestSnap", "ShadowTear" }, new[] { 0.2963f, 0.4444f, 0.4444f });
        public static readonly KokuyoClip Eclipse = new KokuyoClip("Eclipse", 72, 2.4f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "READY", "READY", new string[] { "SwordPlant", "MoonFade", "FistClose" }, new[] { 0.2778f, 0.4167f, 0.4722f });
        public static readonly KokuyoClip LastStand = new KokuyoClip("LastStand", 45, 1.5f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "", "READY", new string[] { "Roar" }, new[] { 0.5111f });
        public static readonly KokuyoClip Defeat = new KokuyoClip("Defeat", 90, 3.0f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "KNEEL", "SEIZA_D", new string[] { "SwordRelease", "MaskSnap", "MaskHit", "MaskHit" }, new[] { 0.2222f, 0.4444f, 0.5556f, 0.6222f });
        public static readonly KokuyoClip DefeatLoop = new KokuyoClip("DefeatLoop", 60, 2.0f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "SEIZA_D", "", new string[0], new float[0]);
        public static readonly KokuyoClip SeizaBow = new KokuyoClip("SeizaBow", 60, 2.0f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "SEIZA_D", "SEIZA_D", new string[0], new float[0]);
        public static readonly KokuyoClip SeizaIdle = new KokuyoClip("SeizaIdle", 90, 3.0f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "", "", new string[0], new float[0]);
        public static readonly KokuyoClip Intro = new KokuyoClip("Intro", 96, 3.2f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "SEIZA", "READY", new string[] { "HeadRise", "Step", "Step", "Chiburi", "EyesIgnite" }, new[] { 0.25f, 0.5104f, 0.7188f, 0.8229f, 0.8438f });
        public static readonly KokuyoClip Tsukuyomi = new KokuyoClip("Tsukuyomi", 75, 2.5f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "READY", "READY", new string[] { "SwordPlant", "RingSlam", "RingSlam", "RingSlam" }, new[] { 0.1867f, 0.4f, 0.6f, 0.8f });
        public static readonly KokuyoClip Walk = new KokuyoClip("Walk", 36, 1.2f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "", "", new string[] { "Step", "Step" }, new[] { 0.0f, 0.5f });
        public static readonly KokuyoClip Stalk = new KokuyoClip("Stalk", 30, 1.0f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "", "", new string[] { "Step", "Step" }, new[] { 0.0f, 0.5f });
        public static readonly KokuyoClip StrafeL = new KokuyoClip("StrafeL", 36, 1.2f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "", "", new string[] { "Step", "Step" }, new[] { 0.0f, 0.5f });
        public static readonly KokuyoClip StrafeR = new KokuyoClip("StrafeR", 36, 1.2f, 0.0f, 0.0f, 0.0f, 1.6f, 0.0f,
            null,
            "", "", new string[] { "Step", "Step" }, new[] { 0.0f, 0.5f });
        /// <summary>KabutoWari: la hoja queda clavada entre estos normalizados (castigo libre).</summary>
        public static readonly float KabutoStuckStart = 0.4667f, KabutoStuckEnd = 0.7333f;
        /// <summary>Ichimonji: radio bajo la empuñadura que la hoja no toca (m).</summary>
        public const float IchimonjiSafeCore = 1.4f;
        /// <summary>Parried: metros que retrocede con la curva 1 - e^(-10 t) (los pies no patinan con eso).</summary>
        public const float ParriedKnock = 0.6f;
    }
}
