using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

public class EnemyMovement : MonoBehaviour
{
    //scripts
    [SerializeField] private EnemyBeingDamaged enemyBeingDamaged;
    [SerializeField] private EnemyCombat enemyCombat;
    [SerializeField] private Animator animator;
    [SerializeField] private Animator ExclamationMarkAnimator;
    [SerializeField] private NavMeshAgent agent;

    //etc
    public Transform player;
    public float distanceToPlayer;
    [SerializeField] private float maxDistance;
    [SerializeField] private float minDistance;
    [SerializeField] public float attackRange;
    [SerializeField] private GameObject exclamationMark;
    public bool canAttack;
    float segundos = 0f;
    [SerializeField] float tiempoDeAnimacionExclamation;
    [SerializeField] public bool stayStill;

    public bool seen;
    public bool isAttacking = false;
    [SerializeField] private bool isAttackingGeneral;

    [SerializeField] public bool canAttackFinal; //MEGA CLAVEEE
    [SerializeField] private float rotationSpeed = 10f;

    // Start is called before the first frame update
    void Start()
    {
        canAttackFinal=true;
        agent.updateRotation = false;
        stayStill = false;
    }

    // Update is called once per frame
    void Update()
    {
        segundos += Time.deltaTime;
        distanceToPlayer = Vector3.Distance(transform.position, player.position);
        if (!seen && distanceToPlayer <= minDistance)
        {
            animator.SetTrigger("Spotted");
            Invoke(nameof(Seen), 0.1f);
            exclamationMark.SetActive(true);
            ExclamationMarkAnimator.SetTrigger("EnemySpottedSignoExclamacion");
            segundos = 0.0f;
        }
        
        if (exclamationMark.activeInHierarchy && segundos >= tiempoDeAnimacionExclamation)
        {
            exclamationMark.SetActive(false);
        }
        if (animator.GetCurrentAnimatorStateInfo(0).IsName("ChasingPlayer"))
        {
            canAttackFinal = true;
        }
        // Si está aturdido o atacando, no hacer movimiento
        if (isAttacking) return;

        // Determinar comportamiento según distancia
        if (distanceToPlayer <= attackRange && seen && canAttackFinal)  
        {
            canAttack = true;
            Idle(); // detener el movimiento mientras ataca
        }
        else if (distanceToPlayer > attackRange && seen && !enemyCombat.isAttacking && !animator.GetCurrentAnimatorStateInfo(0).IsName("Stunned") && !stayStill)
        {
            canAttack = false;
            Chase();
        }
        else
        {
            canAttack = false;
            Idle();
        }
    }
    void Seen()
    {
        seen = true;
    }

    void Chase()
    {
        if (!animator.GetCurrentAnimatorStateInfo(0).IsName("EnemySpotted"))
        {
            agent.isStopped = false;
            agent.SetDestination(player.position);
        }

        // Girar suavemente hacia el jugador
        Vector3 directionToPlayer = (player.position - transform.position).normalized;
        directionToPlayer.y = 0;
        Quaternion targetRotation = Quaternion.LookRotation(directionToPlayer);
        transform.rotation = Quaternion.Slerp(transform.rotation, targetRotation, rotationSpeed * Time.deltaTime);

        // Animaciones de movimiento
        animator.SetBool("isChasing", true);
    }

    void Idle()
    {
        isAttacking = false;
        agent.isStopped = true;
        animator.SetBool("isChasing", false);
    }
}

