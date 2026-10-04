using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class EnemyAttack : MonoBehaviour
{
    [SerializeField] private Animator animator;
    [SerializeField] private Transform Player;
    [SerializeField] private EnemySwordAnimation enemySwordAnimation;
    [SerializeField] private followPlayer followPlayer;
    
    // Start is called before the first frame update
    void Start()
    {
    }

    // Update is called once per frame
    void Update()
    {
        bool Stunned = animator.GetBool("isStunned");

        Vector3 directionToPlayer = Player.position - transform.position;
        if(Vector3.Distance(Player.position, transform.position) <= followPlayer.minDistance && !Stunned)
        {
            enemySwordAnimation.SwordHit();
        }
    }
}
