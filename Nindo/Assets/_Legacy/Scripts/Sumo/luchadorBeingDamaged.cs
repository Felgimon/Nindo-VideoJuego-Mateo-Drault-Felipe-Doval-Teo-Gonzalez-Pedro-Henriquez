using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class luchadorBeingDamaged : MonoBehaviour
{
    //seteados desde el inspector
    [SerializeField] private LuchadorHealthScript healthScript;
    [SerializeField] private LuchadorCombat luchadorCombat;
    [SerializeField] private EnemyHitbox hitbox;
    [SerializeField] private Rigidbody rb;
    [SerializeField] private Transform playerTransform;
    [SerializeField] Animator animator;
    [SerializeField] private GameObject enemyEntity;
    [SerializeField] private bool isBeingDamaged;
    [SerializeField] private float safeTime;
    [SerializeField] private DesequilibroBar desequilibroBar;

    //knockback
    [SerializeField] private float knockbackForce;
    [SerializeField] private float knockbackDuration;


    //animaciones
    [SerializeField] public float stunDuration;
    [SerializeField] public float stunTimer;
    public bool isStunned = false;
    public bool superArmor = false; //no puede recibir mas stun


    //Script vida
    public float Health;
    public float maxHealthAmount;
    [SerializeField] private float damageAmount; //se va a cambiar a la espada este valor
    [SerializeField] private GameObject F;
    public bool isFinishable;
    public float finisherThreshold = 20f;
    [SerializeField] private WhteFlash whiteFlash;


    //Parry


    void Start()
    {
        Health = maxHealthAmount;
        healthScript.UpdateHealthBar(maxHealthAmount, Health);
    }

    // Update is called once per frame
    void Update()
    {
        if (isStunned)
        {
            stunTimer -= Time.deltaTime;
            if (stunTimer <= 0)
            {
                animator.SetBool("isStunned", false);
                isStunned = false;

            }
        }
        if (isBeingDamaged)
        {
            safeTime -= Time.deltaTime;
            if (safeTime <= 0)
            {
                isBeingDamaged = false;
            }
        }
        if (Health <= finisherThreshold)
        {
            F.SetActive(true);
            isFinishable = true;
        }
        if (animator.GetCurrentAnimatorStateInfo(0).IsName("Stunned"))
        {
            safeTime -= Time.deltaTime;
            if (safeTime <= 0)
            {
                animator.SetBool("isStunned", false);
            }
        }

    }
    void OnTriggerEnter(Collider other)
    {
        if (other.CompareTag("PlayerSword") && !isBeingDamaged)
        {
            if (luchadorCombat.currentMomentum > 0)
            {
                luchadorCombat.currentMomentum--;
                desequilibroBar.UpdateDesequilibrioBar(luchadorCombat.maxMomentum, luchadorCombat.currentMomentum);
                StartCoroutine(luchadorCombat.MiniStun());
            }
            //Animaciones
            stunTimer = stunDuration;
            animator.SetBool("isStunned", true);
            isStunned = true;            
            isBeingDamaged = true;
            Health -= damageAmount;
            whiteFlash.Flash();
            if (Health <= 0)
            {
                Invoke(nameof(Death), knockbackDuration);
            }
            healthScript.UpdateHealthBar(maxHealthAmount, Health);


        }

    }
    void Death()
    {
        Destroy(gameObject);
    }
}
