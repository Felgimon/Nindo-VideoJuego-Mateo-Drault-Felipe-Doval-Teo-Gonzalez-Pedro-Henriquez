using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.VFX;
public class PlayerCombat : MonoBehaviour
{
    [Header("Referencias")]
    [SerializeField] private MeshCollider katanaCollider;
    [SerializeField] private PlayerDamaged playerDamaged;
    [SerializeField] private Animator anim;
    [SerializeField] private ParticleSystem chispas;
    [SerializeField] private EnemyCombat enemyCombat;
    [SerializeField] private Rigidbody rb;
    [SerializeField] private ManaBar manaBar;
    [SerializeField] private CameraShake cameraShake;

    [Header("Configuración")]
    [SerializeField] private float pushForce = 3f;
    [SerializeField] private float pushDuration = 0.1f;
    [SerializeField] private float parryPushForce = 2f;
    [SerializeField] private float parryPushDuration = 0.15f;
    [SerializeField] private float parryWindow = 0.3f;     // Ventana activa del parry
    [SerializeField] private float inmunityTime = 0.4f;
    [SerializeField] private float chispasDuration = 0.05f;
    [SerializeField] private float parryManaGain = 10f;

    public bool pushing = false;
    private float pushTime = 0f;

    private bool parryPushingBack = false;
    private float parryPushTime = 0f;

    public bool parryActive = false;   // Ventana activa
    public bool hasParried = false;
    public bool isAttacking = false;
    public bool canCombo;
    [SerializeField] private float comboStep = 0;

    public VisualEffect parryEffect;
    void Start()
    {
        isAttacking = false;
        chispas.Stop();
    }

    void Update()
    {
        //Se chequea si esta tocando algun boton de combate
        if (Input.GetKeyDown(KeyCode.Space))
        {
            SwordHit();
        }

        if (Input.GetKeyDown(KeyCode.E))
        {
            TryParry();
        }

        //hacer que el personaje se mueva hacia adelante al atacar
        if (pushing)
        {
            transform.position += transform.forward * 3f * Time.deltaTime; // velocidad
            pushTime += Time.deltaTime;

            if (pushTime >= 0.1f) // dura 0.1 segundos
                pushing = false;
        }

        //hacer que el personaje se mueva hacia atras al parry
        if (parryPushingBack)
        {
            transform.position -= transform.forward * 2f * Time.deltaTime; // velocidad de retroceso
            parryPushTime += Time.deltaTime;

            if (parryPushTime >= 0.15f) // dura 0.15 segundos
                parryPushingBack = false;
        }
    }
    //___________________________ataque___________________________
    public void SwordHit()
    {
        if (!isAttacking)
        {
            comboStep = 1;
            isAttacking = true;
            anim.SetTrigger("attack");
            StartPush();
            return;
        }

        else if (canCombo)
        {
            ContinueCombo();
        }
    }
    public void ContinueCombo()
    {
        canCombo = false; // evita spamear
        comboStep++;

        if (comboStep == 2)
        {
            anim.SetTrigger("Attack2");
            StartPush();
        }
        else if (comboStep == 3)
        {
            anim.SetTrigger("Attack3");
            StartPush();
        }
        else
        {
            comboStep = 0;
            isAttacking = false;
        }
    }

    void StartPush()
    {
        pushing = true;
        pushTime = 0f;
    }

    public void StartAttacking()   // llamado desde la animación
    {
        katanaCollider.enabled = true;
    }


    public void StopAttacking()    // llamado desde la animación
    {
        katanaCollider.enabled = false;
    }
    // Llamado desde animaciones al final de cada ataque
    public void AttackEnd()
    {
        if (comboStep >= 3) // último golpe
        {
            comboStep = 0;
            isAttacking = false;
        }
        else
        {
            //se corta combo
            StartCoroutine(ResetComboDelay());
        }
        katanaCollider.enabled = false;
    }
    IEnumerator ResetComboDelay()
    {
        yield return new WaitForSeconds(0.4f);
        if (!canCombo)
        {
            comboStep = 0;
            isAttacking = false;
        }
    }
    
   
    public void EnableComboWindow()
    {
        canCombo = true;
    }
    public void DisableComboWindow()
    {
        canCombo = false;
    }



// ------------------parry------------------
        void TryParry()
    {
        if (!parryActive)
        {
            StartCoroutine(ParryWindow());
        }
    }

    IEnumerator ParryWindow()
    {
        anim.SetTrigger("parry");
        parryActive = true;

        // Parry está activo por un breve tiempo
        yield return new WaitForSeconds(parryWindow);
        parryActive = false;
    }

    public void OnHitByEnemy(EnemyBase atacante)
    {
        //Debug.Log("golpe");
        if (parryActive)
        {
            SuccessfulParry(atacante);
        }
        else
        {
            playerDamaged.TakeDamage();
        }
    }

    void SuccessfulParry(EnemyBase atacante)
    {
        manaBar.gastarMana(-parryManaGain);
        anim.SetTrigger("succesfulParry");
        SoundManager.PlaySound(SoundType.PARRY, 0.1f);
        parryEffect.Play();
        hasParried = true;
        StartPushBack();
        chispas.Play();
        Invoke(nameof(EndChispas), chispasDuration);
        Invoke(nameof(EndInmunity), inmunityTime);
        StartCoroutine(HitStop(0.055f)); // pausar 0.05 segundos

        // Interrumpir ataque enemigo
        atacante.InterruptAttack();
        cameraShake.startShaking = true;

    }
    public IEnumerator HitStop(float duration)
    {
        float originalTimeScale = Time.timeScale;
        Time.timeScale = 0f; // pausa total
        yield return new WaitForSecondsRealtime(duration);
        Time.timeScale = originalTimeScale;
    }


    void StartPushBack()
    {
        parryPushingBack = true;
        parryPushTime = 0f;
    }

    void EndInmunity()
    {
        hasParried = false;
    }

    void EndChispas()
    {
        chispas.Stop();
    }

    // ------------------parry del enemigo------------------
    public void InterrumptAttack()
    {
        if (isAttacking)
        {
            anim.SetTrigger("Parryed");
            cameraShake.startShaking = true;
            StartCoroutine(HitStop(0.1f));
            anim.ResetTrigger("Attack1");
            anim.ResetTrigger("Attack2");
            anim.ResetTrigger("Attack3");
            isAttacking = false;
            katanaCollider.enabled = false;
            comboStep = 0;

        }
    }


    }
