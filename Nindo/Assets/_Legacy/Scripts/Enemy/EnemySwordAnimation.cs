using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class EnemySwordAnimation : MonoBehaviour
{
    [SerializeField]followPlayer followPlayer;
    public Animator animator;
    public bool isAttacking;
    public BoxCollider swordCollider;
    public bool isStunned;


    // Start is called before the first frame update
    void Start()
    {
        isAttacking = false;
    }

    // Update is called once per frame
    void Update()
    {
        if (isStunned)
        {
        }
    }
    public void SwordHit()
    {
        if (!animator.GetCurrentAnimatorStateInfo(0).IsName("Attack"))//animacion de la espada
        {
            animator.SetTrigger("hit");
        }
    }
    public void StopAttacking()
    {
        isAttacking=false;
        swordCollider.enabled = false;
        animator.ResetTrigger("hit");
    }
    public void StartAttaking()
    {
        swordCollider.enabled = true;
        isAttacking = true;
    }
    public void InterruptAttack()
    {
        if (isAttacking)
        {
            animator.ResetTrigger("hit");
            isAttacking = false;
            swordCollider.enabled = false;

        }
    }
}
