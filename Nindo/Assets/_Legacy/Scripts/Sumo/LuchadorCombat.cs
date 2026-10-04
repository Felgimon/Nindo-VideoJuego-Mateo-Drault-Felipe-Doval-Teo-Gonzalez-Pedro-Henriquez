using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class LuchadorCombat : EnemyBase
{
    [Header("Referencias")]
    [SerializeField] private PlayerCombat playerCombat;
    [SerializeField] private Animator animator;
    [SerializeField] private UnityEngine.AI.NavMeshAgent agent;
    [SerializeField] private luchadorMovement luchadorMovement;
    private Coroutine attackRoutine;

    [Header("Rango de ataque")]
    [SerializeField] private float attackRange = 2f;   // Distancia m�xima para golpear
    [SerializeField] private float attackAngle = 45f;  // �ngulo frontal de golpe
    public bool hasDealtDamage = false;

    [Header("Postura")]
    [SerializeField] private float posturaInicial = 5f;
    private float posturaActual;
    [SerializeField] private PosturaScript posturaScript; // Para UI de barra de postura

    [Header("Estados")]
    public bool isAttacking = false;

    public ParticleSystem chispas;
    [SerializeField] float chispasDuration;
    public float currentMomentum;
    private bool isMiniStunned = false;
    [SerializeField] private float miniStunDuration = 0.25f;
    //push
    private bool pushing = false;
    private float pushTime = 0f;
    [SerializeField] public int maxMomentum = 3;
    [SerializeField] private DesequilibroBar desequilibroBar;
    public bool isBusy;
    public bool cancelAttackCombo =false;

    // Start is called before the first frame update
    void Start()
    {
        posturaActual = posturaInicial;
        currentMomentum = 0;
        desequilibroBar.UpdateDesequilibrioBar(maxMomentum, currentMomentum);
    }

    // Update is called once per frame
    void Update()
    {
        if (!isAttacking && luchadorMovement.canAttack && attackRoutine == null && !isBusy)
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
        if (currentMomentum <= 0)
        {
            isBusy = false;
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

        // gira hasta que est� alineado
        while (Quaternion.Angle(transform.rotation, targetRotation) > 3f)
        {
            transform.rotation = Quaternion.Slerp(transform.rotation, targetRotation, 6f * Time.deltaTime);
            yield return null;
        }
    }
    IEnumerator AttackComboCoroutine()
    {
        isAttacking = true;
        cancelAttackCombo = false;
        for (int i = 1; i <= 3; i++) // combo de 3 ataques
        {
            if(cancelAttackCombo) break;

            animator.ResetTrigger("Attack1");
            animator.ResetTrigger("Attack2");
            animator.ResetTrigger("Attack3");
            yield return RotateTowardsPlayerBeforeAttack();

            // Lanzar animaci�n
            animator.SetTrigger("Attack" + i);
            // Resetear flag de da�o (solo puede golpear una vez por anim)
            hasDealtDamage = false;
            if (i <3)
            {
                yield return new WaitForSeconds(0.6f);
                // Esperar fin de animaci�n de ataque (ajust� seg�n duraci�n real)

            }
            else 
            {
                yield return new WaitForSeconds(1.2f);

            }
            // Si el jugador se aleja demasiado, cortamos el combo
            float dist = Vector3.Distance(transform.position, playerCombat.transform.position);
            if (dist > attackRange * 1.5f)
            {
                //Debug.Log("Jugador se alej�, cortando combo");
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

        Debug.Log($"Distancia: {dist}, �ngulo: {angle}");

        if (dist <= attackRange && angle <= attackAngle)
        {
            hasDealtDamage = true; // pego
            playerCombat.OnHitByEnemy(this);
        }
    }
    public override void InterruptAttack() //Lo llama la jugador al hacer parry
    {

        isAttacking = false;

        // Resetea triggers de animaci�n de ataques
        animator.ResetTrigger("Attack1");
        animator.ResetTrigger("Attack2");
        animator.ResetTrigger("Attack3");

        posturaScript?.UpdatePosturaBar(posturaInicial, posturaActual);
        if (currentMomentum < maxMomentum)
        {
            currentMomentum++;
            desequilibroBar.UpdateDesequilibrioBar(maxMomentum, currentMomentum);
        }

        Debug.Log("Ataque interrumpido por parry!");
    }
    public IEnumerator MiniStun()
    {
        if (isMiniStunned) yield break;
        isMiniStunned = true;
        animator.SetTrigger("MiniStun");
        yield return new WaitForSeconds(miniStunDuration); //HARDCODEADO
        isMiniStunned = false;
    }
    public void ComboEnd()
    {
        //enemyMovement.stayStill = true;
        if (currentMomentum > 0)
        {
            animator.SetTrigger("Exausto");
            animator.ResetTrigger("Attack1");
            animator.ResetTrigger("Attack2");
            animator.ResetTrigger("Attack3");
            isBusy = true;
            cancelAttackCombo = false;
        }
    }
    public void EndChispas()
    {
        chispas.Stop();
    }
}
