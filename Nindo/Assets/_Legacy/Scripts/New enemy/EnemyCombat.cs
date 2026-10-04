using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

public class EnemyCombat : EnemyBase
{
    [Header("Referencias")]
    [SerializeField] private PlayerCombat playerCombat;
    [SerializeField] private Animator animator;
    [SerializeField] private NavMeshAgent agent;
    [SerializeField] private EnemyMovement enemyMovement;
    [SerializeField] private EnemyBeingDamaged enemyBeingDamaged;
    private Coroutine attackRoutine;
    
    [Header("Rango de ataque")]
    [SerializeField] private float attackRange = 2f;   // Distancia máxima para golpear
    [SerializeField] private float attackAngle = 45f;  // Ángulo frontal de golpe
    public bool hasDealtDamage = false;

    [Header("Postura")]
    [SerializeField] private float posturaInicial = 5f;
    private float posturaActual;
    [SerializeField] private PosturaScript posturaScript; // Para UI de barra de postura

    [Header("Estados")]
    public bool isAttacking = false;

    public ParticleSystem chispas;
    [SerializeField] float chispasDuration;

    [Header("Momentum")]
    [SerializeField] public int maxMomentum = 3;
    [SerializeField] private float decayTime = 3f; // si no golpeas se pierde
    public int currentMomentum = 0;
    private float lastParryTime;
    [SerializeField] private DesequilibroBar desequilibroBar;
    private bool isMiniStunned = false;
    [SerializeField] private float miniStunDuration = 0.25f;

    public bool parry3 = false;
    //push
    private bool pushing = false;
    private float pushTime = 0f;


    void Start()
    {
        currentMomentum = 0;
        desequilibroBar.UpdateDesequilibrioBar(maxMomentum, currentMomentum);
        chispas.Clear();

    }

    // Update is called once per frame
    void Update()
    {
        //Debug.Log(attackRoutine);
        if (!isAttacking && enemyMovement.canAttack && attackRoutine == null)
        {
            attackRoutine = StartCoroutine(AttackComboCoroutine());
        }

        if (pushing)
        {
            transform.position += transform.forward * 3f * Time.deltaTime; // velocidad
            pushTime += Time.deltaTime;

            if (pushTime >= 0.05f) // dura 0.1 segundos
                pushing = false;
        }




    }
    void StartPush()
    {
        pushing = true;
        pushTime = 0f;
    }
    IEnumerator RotateTowardsPlayerBeforeAttack()
    {
        if (playerCombat == null) yield break;

        Vector3 dir = (playerCombat.transform.position - transform.position);
        dir.y = 0;
        if (dir.sqrMagnitude < 0.001f) yield break;

        Quaternion targetRotation = Quaternion.LookRotation(dir.normalized);

        // gira hasta que esté alineado
        while (Quaternion.Angle(transform.rotation, targetRotation) > 3f)
        {
            transform.rotation = Quaternion.Slerp(transform.rotation, targetRotation, 6f * Time.deltaTime);
            yield return null;
        }
    }
    IEnumerator AttackComboCoroutine()
    {
        isAttacking = true;

        for (int i = 1; i <= 3; i++) // combo de 3 ataques
        {
            animator.ResetTrigger("Attack1");
            animator.ResetTrigger("Attack2");
            animator.ResetTrigger("Attack3");
            yield return RotateTowardsPlayerBeforeAttack();

            // Lanzar animación
            animator.SetTrigger("Attack" + i);
            // Resetear flag de daño (solo puede golpear una vez por anim)
            hasDealtDamage = false;

            // Esperar fin de animación de ataque (ajustá según duración real)
            yield return new WaitForSeconds(0.8f);

            // Si el jugador se aleja demasiado, cortamos el combo
            float dist = Vector3.Distance(transform.position, playerCombat.transform.position);
            if (dist > attackRange * 1.5f)
            {
                //Debug.Log("Jugador se alejó, cortando combo");
                break;
            }

        }
        attackRoutine = null;
        isAttacking = false;
    }

    public void TryDealDamageToPlayer()
    {
        StartPush();

        if (hasDealtDamage) return; // evita repetir el danio
        if (playerCombat == null) return;

        float dist = Vector3.Distance(playerCombat.transform.position, transform.position);
        Vector3 toPlayer = (playerCombat.transform.position - transform.position).normalized;
        float angle = Vector3.Angle(transform.forward, toPlayer);

        //Debug.Log($"Distancia: {dist}, Ángulo: {angle}");

        if (dist <= attackRange && angle <= attackAngle)
        {
            hasDealtDamage = true; // pego
            playerCombat.OnHitByEnemy(this);
        }
    }

    public override void InterruptAttack() //Lo llama la jugador al hacer parry
    {
            if(animator.GetCurrentAnimatorStateInfo(0).IsName("Attack3"))
                {
                    
                }
            isAttacking = false;

            // Resetea triggers de animación de ataques
            animator.ResetTrigger("Attack1");
            animator.ResetTrigger("Attack2");
            animator.ResetTrigger("Attack3");
            

        if (currentMomentum < maxMomentum)
            {
                currentMomentum++;
                desequilibroBar.UpdateDesequilibrioBar(maxMomentum, currentMomentum);
            }

            //Debug.Log("Ataque interrumpido por parry!");
    }

    public void ComboEnd()
    {
        enemyMovement.stayStill=true;
        enemyMovement.canAttackFinal = false;
        if (currentMomentum > 0)
        {
            animator.SetTrigger("Exausto");
            animator.ResetTrigger("Attack3");
        }
        else
        {
            enemyBeingDamaged.canParry=true;
            animator.SetTrigger("WaitParry");
            animator.ResetTrigger("Attack3");
        }
    }

    public IEnumerator MiniStun()
    {
        if (isMiniStunned) yield break;
        isMiniStunned = true;
        animator.SetTrigger("MiniStun");
        yield return new WaitForSeconds(miniStunDuration); //HARDCODEADO
        isMiniStunned = false;
    }

    public void EndChispas()
    {
        chispas.Stop();
    }
    public void OnParryAnimationEnd()
    {
        // empezar el ataque inmediatamente
        if (!isAttacking)
            attackRoutine = StartCoroutine(AttackComboCoroutine());
    }

}
