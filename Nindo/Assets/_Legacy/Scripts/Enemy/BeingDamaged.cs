using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class BeingDamaged : MonoBehaviour
{
    //animaciones
    [SerializeField] private Rigidbody rb;
    [SerializeField] private Transform playerTransform;
    [SerializeField] private float knockbackForce;
    [SerializeField] private float knockbackDuration;

    //animaciones
    [SerializeField] Animator animator;
    [SerializeField] private float stunDuration;
    [SerializeField] private float stunTimer;
    public bool isBeingDamaged = false;
    public bool superArmor = false; //no puede recibir mas stun


    //Script vida
    public float Health;
    public float maxHealthAmount;
    [SerializeField] private float damageAmount; //se va a cambiar a la espada este valor
    [SerializeField] private GameObject enemyEntity;
    [SerializeField] private healthScript healthScript;
    [SerializeField] EnemySwordAnimation enemySwordAnimation;

    //Parry
    [SerializeField] private float maxHitsBeforeParry;
    [SerializeField] private float actualHitsBeforeParry;
    [SerializeField] private Animator swordAnimator;
    [SerializeField] private EnemyHitbox hitbox;

    // Start is called before the first frame update
    void Start()
    {
        actualHitsBeforeParry = maxHitsBeforeParry;
        Health = maxHealthAmount;
        healthScript.UpdateHealthBar(maxHealthAmount, Health);
    }

    // Update is called once per frame
    void Update()
    {
        if (isBeingDamaged)
        {
            stunTimer-= Time.deltaTime;
            if (stunTimer <= 0)
            {
                animator.SetBool("isStunned", false);
                isBeingDamaged=false;
                enemySwordAnimation.isAttacking = false;

            }
        }
    }
    void OnTriggerEnter(Collider other)
    {
        if(other.CompareTag("Player")& !hitbox.isParying)        
        {
            actualHitsBeforeParry -=1;
            if (actualHitsBeforeParry <= 0)
            {
                TriggerParry();
            }
            //Animaciones
            stunTimer = stunDuration;
            animator.SetBool("isStunned", true);
            animator.ResetTrigger("hit");            
            isBeingDamaged = true;

            //Knockback
            rb.velocity = Vector3.zero;
            Vector3 knockback = (transform.position - playerTransform.position).normalized;
            knockback.y = 0f;
            rb.AddForce(knockback * knockbackForce, ForceMode.Impulse);

            //Sacar vida y eliminar en caso de tener 0
            Health -= damageAmount;
            if (Health <= 0)
            {
                Invoke(nameof(Death), knockbackDuration);
            }
            healthScript.UpdateHealthBar(maxHealthAmount, Health);


        }

    }

    void Death()
    {
        Destroy(enemyEntity);
    }
    void TriggerParry()
    {
        
        swordAnimator.SetTrigger("triggerParry");
        actualHitsBeforeParry=maxHitsBeforeParry;
        hitbox.currentMode=  EnemyHitbox.HitboxMode.Parry;
        superArmor = true;
    }
}
