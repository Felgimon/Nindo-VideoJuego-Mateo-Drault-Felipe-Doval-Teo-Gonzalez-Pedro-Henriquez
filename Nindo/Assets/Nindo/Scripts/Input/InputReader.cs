using UnityEngine;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace Nindo
{
    public enum Act
    {
        Attack, Parry, Dash, Lock, Finisher, Interact, Ability1, Ability2, Pause, LockNext, LockPrev, Submit, Cancel
    }

    /// <summary>
    /// Lectura de input unificada: teclado+mouse y gamepad (Input System), con fallback al
    /// Input Manager clásico. Incluye buffer de acciones para que los combos/parrys se sientan
    /// precisos (si apretás un poco antes de que termine el golpe, igual entra).
    /// </summary>
    [DefaultExecutionOrder(-800)]
    public class InputReader : MonoBehaviour
    {
        const int ActCount = 13;
        readonly float[] pressedAt = new float[ActCount];
        readonly bool[] pressedNow = new bool[ActCount];
        readonly bool[] consumed = new bool[ActCount];

        public Vector2 Move { get; private set; }
        public bool ParryHeld { get; private set; }
        public bool AttackHeld { get; private set; }
        public bool LockHeld { get; private set; }
        public bool UsingGamepad { get; private set; }
        /// <summary>Bloquea el input de gameplay (UI abierta, cinemáticas).</summary>
        public bool GameplayBlocked { get; set; }

        float rumbleUntil;

        void Awake()
        {
            Game.Input = this;
            for (int i = 0; i < ActCount; i++) pressedAt[i] = -999f;
        }

        void OnDestroy()
        {
            if (Game.Input == this) Game.Input = null;
            StopRumble();
        }

        void OnDisable() => StopRumble();

        void Update()
        {
            for (int i = 0; i < ActCount; i++) pressedNow[i] = false;
            Vector2 move = Vector2.zero;
            bool parryHeld = false, attackHeld = false, lockHeld = false;

#if ENABLE_INPUT_SYSTEM
            var kb = Keyboard.current;
            var mouse = Mouse.current;
            var pad = Gamepad.current;
            if (kb != null)
            {
                if (kb.wKey.isPressed || kb.upArrowKey.isPressed) move.y += 1;
                if (kb.sKey.isPressed || kb.downArrowKey.isPressed) move.y -= 1;
                if (kb.dKey.isPressed || kb.rightArrowKey.isPressed) move.x += 1;
                if (kb.aKey.isPressed || kb.leftArrowKey.isPressed) move.x -= 1;
                if (kb.jKey.wasPressedThisFrame) Press(Act.Attack, false);
                if (kb.kKey.wasPressedThisFrame) Press(Act.Parry, false);
                if (kb.spaceKey.wasPressedThisFrame || kb.leftShiftKey.wasPressedThisFrame || kb.lKey.wasPressedThisFrame) Press(Act.Dash, false);
                if (kb.qKey.wasPressedThisFrame || kb.tabKey.wasPressedThisFrame) Press(Act.Lock, false);
                if (kb.fKey.wasPressedThisFrame) { Press(Act.Finisher, false); }
                if (kb.eKey.wasPressedThisFrame || kb.fKey.wasPressedThisFrame) Press(Act.Interact, false);
                if (kb.digit1Key.wasPressedThisFrame || kb.uKey.wasPressedThisFrame) Press(Act.Ability1, false);
                if (kb.digit2Key.wasPressedThisFrame || kb.iKey.wasPressedThisFrame) Press(Act.Ability2, false);
                if (kb.escapeKey.wasPressedThisFrame || kb.pKey.wasPressedThisFrame) Press(Act.Pause, false);
                if (kb.enterKey.wasPressedThisFrame) Press(Act.Submit, false);
                if (kb.escapeKey.wasPressedThisFrame) Press(Act.Cancel, false);
                parryHeld |= kb.kKey.isPressed;
                attackHeld |= kb.jKey.isPressed;
                lockHeld |= kb.qKey.isPressed || kb.tabKey.isPressed;
                if (kb.anyKey.wasPressedThisFrame) UsingGamepad = false;
            }
            if (mouse != null)
            {
                if (mouse.leftButton.wasPressedThisFrame) Press(Act.Attack, false);
                if (mouse.rightButton.wasPressedThisFrame) Press(Act.Parry, false);
                if (mouse.middleButton.wasPressedThisFrame) Press(Act.Lock, false);
                float wheel = mouse.scroll.ReadValue().y;
                if (wheel > 0.1f) Press(Act.LockPrev, false);
                if (wheel < -0.1f) Press(Act.LockNext, false);
                parryHeld |= mouse.rightButton.isPressed;
                lockHeld |= mouse.middleButton.isPressed;
                attackHeld |= mouse.leftButton.isPressed;
                if (mouse.leftButton.wasPressedThisFrame || mouse.rightButton.wasPressedThisFrame) UsingGamepad = false;
            }
            if (pad != null)
            {
                Vector2 ls = pad.leftStick.ReadValue();
                if (ls.sqrMagnitude < 0.04f) ls = Vector2.zero;
                ls += pad.dpad.ReadValue();
                if (ls.sqrMagnitude > 0.01f) { move += ls; UsingGamepad = true; }
                if (pad.buttonWest.wasPressedThisFrame || pad.rightShoulder.wasPressedThisFrame) Press(Act.Attack, true);
                if (pad.leftShoulder.wasPressedThisFrame) Press(Act.Parry, true);
                if (pad.buttonEast.wasPressedThisFrame || pad.buttonSouth.wasPressedThisFrame) Press(Act.Dash, true);
                if (pad.rightStickButton.wasPressedThisFrame) Press(Act.Lock, true);
                if (pad.buttonNorth.wasPressedThisFrame) { Press(Act.Finisher, true); Press(Act.Interact, true); }
                if (pad.rightTrigger.wasPressedThisFrame) Press(Act.Ability1, true);
                if (pad.leftTrigger.wasPressedThisFrame) Press(Act.Ability2, true);
                if (pad.startButton.wasPressedThisFrame) Press(Act.Pause, true);
                if (pad.buttonSouth.wasPressedThisFrame) Press(Act.Submit, true);
                if (pad.buttonEast.wasPressedThisFrame) Press(Act.Cancel, true);
                Vector2 rs = pad.rightStick.ReadValue();
                if (rs.x > 0.7f && !stickFlicked) { Press(Act.LockNext, true); stickFlicked = true; }
                else if (rs.x < -0.7f && !stickFlicked) { Press(Act.LockPrev, true); stickFlicked = true; }
                else if (Mathf.Abs(rs.x) < 0.3f) stickFlicked = false;
                parryHeld |= pad.leftShoulder.isPressed;
                lockHeld |= pad.rightStickButton.isPressed;
                attackHeld |= pad.buttonWest.isPressed || pad.rightShoulder.isPressed;
            }
#elif ENABLE_LEGACY_INPUT_MANAGER
            move.x = Input.GetAxisRaw("Horizontal");
            move.y = Input.GetAxisRaw("Vertical");
            if (Input.GetKeyDown(KeyCode.J) || Input.GetMouseButtonDown(0)) Press(Act.Attack, false);
            if (Input.GetKeyDown(KeyCode.K) || Input.GetMouseButtonDown(1)) Press(Act.Parry, false);
            if (Input.GetKeyDown(KeyCode.Space) || Input.GetKeyDown(KeyCode.LeftShift)) Press(Act.Dash, false);
            if (Input.GetKeyDown(KeyCode.Q) || Input.GetKeyDown(KeyCode.Tab) || Input.GetMouseButtonDown(2)) Press(Act.Lock, false);
            if (Input.GetKeyDown(KeyCode.F)) { Press(Act.Finisher, false); Press(Act.Interact, false); }
            if (Input.GetKeyDown(KeyCode.E)) Press(Act.Interact, false);
            if (Input.GetKeyDown(KeyCode.Alpha1)) Press(Act.Ability1, false);
            if (Input.GetKeyDown(KeyCode.Alpha2)) Press(Act.Ability2, false);
            if (Input.GetKeyDown(KeyCode.Escape)) { Press(Act.Pause, false); Press(Act.Cancel, false); }
            if (Input.GetKeyDown(KeyCode.Return)) Press(Act.Submit, false);
            float wheel = Input.mouseScrollDelta.y;
            if (wheel > 0.1f) Press(Act.LockPrev, false);
            if (wheel < -0.1f) Press(Act.LockNext, false);
            parryHeld = Input.GetKey(KeyCode.K) || Input.GetMouseButton(1);
            attackHeld = Input.GetKey(KeyCode.J) || Input.GetMouseButton(0);
            lockHeld = Input.GetKey(KeyCode.Q) || Input.GetKey(KeyCode.Tab) || Input.GetMouseButton(2);
#endif
            Move = Vector2.ClampMagnitude(move, 1f);
            ParryHeld = parryHeld;
            AttackHeld = attackHeld;
            LockHeld = lockHeld;

            if (rumbleUntil > 0f && Time.unscaledTime > rumbleUntil) StopRumble();
        }

#if ENABLE_INPUT_SYSTEM
        bool stickFlicked;
#endif

        void Press(Act a, bool gamepad)
        {
            int i = (int)a;
            pressedNow[i] = true;
            pressedAt[i] = Time.unscaledTime;
            // si el buffer se limpió en este mismo frame (p. ej. la UI procesó el botón que cerró la
            // pausa antes que este Update) la pulsación no llega al gameplay
            consumed[i] = Time.frameCount == clearedFrame;
            if (gamepad) UsingGamepad = true;
        }

        /// <summary>¿Se apretó este frame? (ignora el bloqueo de gameplay para UI). Si en este frame
        /// ya se llamó a ClearBuffer (p. ej. la A del mando cerró la pausa) la pulsación se descarta
        /// también acá, para que los que leen después (tutoriales de StoryDirector) no la tomen.</summary>
        public bool Pressed(Act a) => pressedNow[(int)a] && Time.frameCount != clearedFrame;

        /// <summary>¿Se apretó dentro de los últimos 'window' segundos y nadie lo consumió?</summary>
        public bool Buffered(Act a, float window = 0.18f)
        {
            if (GameplayBlocked) return false;
            int i = (int)a;
            return !consumed[i] && Time.unscaledTime - pressedAt[i] <= window;
        }

        public void Consume(Act a) => consumed[(int)a] = true;

        /// <summary>Descarta las acciones en buffer (también las que se registren en este mismo frame).</summary>
        public void ClearBuffer()
        {
            for (int i = 0; i < ActCount; i++) consumed[i] = true;
            clearedFrame = Time.frameCount;
        }

        int clearedFrame = -1;

        public Vector2 GameplayMove => GameplayBlocked ? Vector2.zero : Move;

        // ---------------------------------------------------------------- rumble
        public void Rumble(float low, float high, float seconds)
        {
#if ENABLE_INPUT_SYSTEM
            if (!Settings.Rumble || !UsingGamepad) return;
            var pad = Gamepad.current;
            if (pad == null) return;
            pad.SetMotorSpeeds(Mathf.Clamp01(low), Mathf.Clamp01(high));
            rumbleUntil = Time.unscaledTime + seconds;
#endif
        }

        void StopRumble()
        {
            rumbleUntil = 0f;
#if ENABLE_INPUT_SYSTEM
            Gamepad.current?.SetMotorSpeeds(0f, 0f);
#endif
        }

        // ---------------------------------------------------------------- glyphs
        public string Glyph(Act a)
        {
            if (UsingGamepad)
            {
                switch (a)
                {
                    case Act.Attack: return "□ / X";
                    case Act.Parry: return "L1 / LB";
                    case Act.Dash: return "○ / B";
                    case Act.Lock: return "R3";
                    case Act.Finisher: return "△ / Y";
                    case Act.Interact: return "△ / Y";
                    case Act.Ability1: return "R2 / RT";
                    case Act.Ability2: return "L2 / LT";
                    case Act.Pause: return "Start";
                    case Act.LockNext: return "Stick der.";
                    default: return a.ToString();
                }
            }
            switch (a)
            {
                case Act.Attack: return "Click izq. / J";
                case Act.Parry: return "Click der. / K";
                case Act.Dash: return "Espacio";
                case Act.Lock: return "Q";
                case Act.Finisher: return "F";
                case Act.Interact: return "E";
                case Act.Ability1: return "1";
                case Act.Ability2: return "2";
                case Act.Pause: return "Esc";
                case Act.LockNext: return "Rueda";
                default: return a.ToString();
            }
        }
    }
}
